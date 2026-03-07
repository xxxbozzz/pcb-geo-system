"""
GEO 知识引擎 — 批量生产入口 (v3.0)
===================================
唯一入口文件。从 geo_keywords 表消费关键词，逐篇生成文章。

核心流程（每个关键词）：
    采集 → 结构化 → 生成 → 质检 → 返修(×3) → 下一篇

使用方法：
    # 本地运行
    python batch_generator.py

    # 后台运行（阿里云 / 服务器）
    nohup python -u batch_generator.py > batch.log 2>&1 &

环境变量（.env 文件）：
    DEEPSEEK_API_KEY  —  DeepSeek / OpenAI 兼容 API 密钥
    DB_HOST           —  MySQL 数据库地址（本地用 localhost）
    DB_USER           —  数据库用户
    DB_PASSWORD       —  数据库密码
    DB_NAME           —  数据库名称
"""

import os
import gc
import time
import json
import logging
from datetime import datetime, timedelta

# ─── 禁用 OpenTelemetry（防止 Python 3.13 导入卡死）───
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("MYSQL_CONNECTOR_PYTHON_TELEMETRY", "0")

from dotenv import load_dotenv
from crewai import Crew
from langchain_openai import ChatOpenAI

from core.agents import GeoAgents
from core.tasks import GeoTasks
from core.db_manager import db_manager
from core.quality_checker import QualityChecker
from core.auto_fixer import AutoFixer
from core.linker import AutoLinker
from core.budget import tracker
from core.build_info import format_build_label
from core.capability_store import capability_store
from core.run_state import (
    clear_current_run_id,
    clear_saved_article_result,
    pop_saved_article_result,
    set_current_run_id,
)
from core.trend_scout import TrendScout


# ═══════════════════════════════════════════
#  配置区
# ═══════════════════════════════════════════

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")
os.environ["OPENAI_API_BASE"] = "https://api.deepseek.com"
os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com"

MAX_REPAIR_ATTEMPTS = 3     # 单篇最大返修次数
PASS_THRESHOLD = 80         # 质检通过分数线
COOLDOWN_SECONDS = 5        # 文章间冷却（防 API 限流）
SCOUT_MAX_RETRIES = 3       # 侦察最大重试次数
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "120"))             # 基准文章量，到达后切入 GEO 真空词自动生产模式
DAILY_GAP_ARTICLES = int(os.getenv("DAILY_GAP_ARTICLES", "5"))   # 每天自动生产的 GEO 真空词文章数量
GEO_GAP_PRIORITY = 9999                                           # TrendScout 注入的高优先级真空词标记
GAP_MODE_RETRY_SECONDS = int(os.getenv("GAP_MODE_RETRY_SECONDS", "3600"))


# ═══════════════════════════════════════════
#  日志配置
# ═══════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("batch_generator.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("GEO")

# 抑制第三方库噪音
for lib in ("openai", "httpx", "httpcore", "urllib3"):
    logging.getLogger(lib).setLevel(logging.WARNING)


# ═══════════════════════════════════════════
#  LLM 初始化
# ═══════════════════════════════════════════

llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com",
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    temperature=0.1,
    timeout=120,
)


# ═══════════════════════════════════════════
#  数据库辅助操作
# ═══════════════════════════════════════════

def get_pending_keywords(limit: int = 1) -> list:
    """获取未处理的关键词"""
    cnx = db_manager.get_connection()
    if not cnx:
        return []
    try:
        cursor = cnx.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, keyword FROM geo_keywords "
            "WHERE target_article_id IS NULL ORDER BY id ASC LIMIT %s",
            (limit,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        cnx.close()


def get_pending_gap_keywords(limit: int = 5) -> list:
    """获取 GEO 真空词队列（高优先级自动生产关键词）"""
    cnx = db_manager.get_connection()
    if not cnx:
        return []
    try:
        cursor = cnx.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, keyword FROM geo_keywords "
            "WHERE target_article_id IS NULL AND search_volume >= %s "
            "ORDER BY created_at ASC, id ASC LIMIT %s",
            (GEO_GAP_PRIORITY, limit),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        cnx.close()


def get_article(article_id: int) -> dict | None:
    """按 ID 获取文章"""
    cnx = db_manager.get_connection()
    if not cnx:
        return None
    try:
        cursor = cnx.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, title, slug, content_markdown, publish_status "
            "FROM geo_articles WHERE id = %s LIMIT 1",
            (article_id,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        cnx.close()


def update_article(article_id: int, **fields):
    """通用文章字段更新"""
    cnx = db_manager.get_connection()
    if not cnx:
        return
    try:
        cursor = cnx.cursor()
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        cursor.execute(
            f"UPDATE geo_articles SET {set_clause} WHERE id = %s",
            (*fields.values(), article_id),
        )
        cnx.commit()
    finally:
        cursor.close()
        cnx.close()


def mark_keyword_done(keyword_id: int, article_id: int):
    """标记关键词已处理"""
    cnx = db_manager.get_connection()
    if not cnx:
        return
    try:
        cursor = cnx.cursor()
        cursor.execute(
            "UPDATE geo_keywords SET target_article_id = %s WHERE id = %s",
            (article_id, keyword_id),
        )
        cnx.commit()
    finally:
        cursor.close()
        cnx.close()


def inject_seed_keywords(limit: int = 5) -> int:
    """从 seed_topics.json 注入种子关键词"""
    try:
        with open("seed_topics.json", "r", encoding="utf-8") as f:
            seeds = json.load(f)
        added = 0
        for item in seeds:
            kw = item.get("keyword")
            if kw and db_manager.add_keyword(kw):
                added += 1
                if added >= limit:
                    break
        return added
    except Exception as e:
        log.error(f"种子注入失败: {e}")
        return 0


# ═══════════════════════════════════════════
#  核心流程
# ═══════════════════════════════════════════

def check_api_health() -> bool:
    """API 连通性检查"""
    try:
        llm.invoke("ping")
        return True
    except Exception as e:
        log.error(f"API 健康检查失败: {e}")
        return False


def run_scout(agents: GeoAgents, tasks: GeoTasks):
    """侦察循环 — 发现新关键词"""
    log.info("🕵️ 触发侦察循环...")
    scout = agents.scout_agent(llm)
    crew = Crew(agents=[scout], tasks=[tasks.scout_task(scout)], verbose=True)
    try:
        crew.kickoff()
        log.info("✅ 侦察完成")
    except Exception as e:
        log.error(f"侦察失败: {e}")


def generate_article(agents: GeoAgents, tasks: GeoTasks, keyword: str):
    """执行 采集→结构化→生成 流水线"""
    collector = agents.collector_agent(llm)
    templater = agents.templater_agent(llm)
    generator = agents.generator_agent(llm)

    capability_context = capability_store.build_context(keyword, limit=5)
    log.info(f"🧠 深亚工艺能力上下文已加载: {keyword}")

    t_collect = tasks.collect_data_task(collector, keyword, capability_context=capability_context)
    t_structure = tasks.structure_content_task(templater, context=[t_collect])
    t_write = tasks.generate_article_task(generator, context=[t_structure], capability_context=capability_context)

    crew = Crew(
        agents=[collector, templater, generator],
        tasks=[t_collect, t_structure, t_write],
        verbose=True,
    )
    crew.kickoff()


def quality_loop(article: dict) -> bool:
    """
    质检→返修闭环，最多 MAX_REPAIR_ATTEMPTS 次。
    返回 True=通过, False=放弃。
    """
    checker = QualityChecker()
    fixer = AutoFixer()

    article_id = article["id"]
    title = article["title"] or ""
    content = article["content_markdown"] or ""

    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        # ── 评分 ──
        score, report = checker.evaluate_article(title, content)
        failed = [k for k, v in report.items() if not v]
        passed = [k for k, v in report.items() if v]

        log.info(
            f"📊 第 {attempt}/{MAX_REPAIR_ATTEMPTS} 次质检: {score}分 "
            f"| ✅{','.join(passed)} | ❌{','.join(failed)}"
        )

        update_article(article_id, quality_score=score)

        # ── 通过 ──
        if score >= PASS_THRESHOLD:
            update_article(article_id, publish_status=1, quality_score=score)
            log.info(f"🎉 质检通过！[{score}分] {title}")
            return True

        # ── 已达上限 ──
        if attempt >= MAX_REPAIR_ATTEMPTS:
            log.warning(f"💀 达到最大返修次数，放弃: [{score}分] {title}")
            return False

        # ── 生成返修指令 ──
        fix_prompt = fixer.generate_fix_prompt(content, report)
        if not fix_prompt:
            log.warning("AutoFixer 未生成返修指令，跳过")
            return False

        # ── LLM 执行返修 ──
        log.info(f"🔧 第 {attempt} 次返修...")
        try:
            result = llm.invoke(fix_prompt)
            new_content = result.content if hasattr(result, "content") else str(result)

            # ── 记录 Token 用量（月度统计）──
            usage = getattr(result, "usage_metadata", None) or getattr(result, "response_metadata", {}).get("token_usage", {})
            in_tok  = getattr(usage, "input_tokens",  None) or (usage.get("prompt_tokens") if isinstance(usage, dict) else 0) or 0
            out_tok = getattr(usage, "output_tokens", None) or (usage.get("completion_tokens") if isinstance(usage, dict) else 0) or 0
            tracker.record(in_tok, out_tok, label=f"repair:{title[:20]}")

            if len(new_content.strip()) < 500:
                log.warning(f"返修结果过短 ({len(new_content)} 字符)，跳过")
                continue

            import hashlib
            content_hash = hashlib.md5(new_content.encode("utf-8")).hexdigest()
            update_article(article_id, content_markdown=new_content, content_hash=content_hash)
            content = new_content
            log.info(f"✅ 返修完成，{len(new_content)} 字符")

        except Exception as e:
            log.error(f"LLM 返修失败: {e}")
            continue

    return False


def process_keyword(agents: GeoAgents, tasks: GeoTasks, kw_row: dict) -> bool:
    """处理单个关键词：生成 + 质检闭环"""
    keyword = kw_row["keyword"]
    kw_id = kw_row["id"]
    run_id = f"kw-{kw_id}-{int(time.time() * 1000)}"
    log.info(f"⚡ 开始处理: {keyword}")

    clear_saved_article_result(run_id)
    set_current_run_id(run_id)
    try:
        generate_article(agents, tasks, keyword)
    except Exception as e:
        log.error(f"生成失败 [{keyword}]: {e}")
        return False
    finally:
        clear_current_run_id()

    save_result = pop_saved_article_result(run_id)
    if not save_result:
        log.error(f"生成结束后未捕获入库结果: {keyword}")
        return False

    if not save_result.get("success"):
        reason = save_result.get("reason", "unknown")
        log.error(f"文章未成功入库 [{keyword}]: {reason}")
        return False

    article_id = save_result.get("article_id")
    if not article_id:
        log.error(f"文章入库缺少 article_id: {keyword}")
        return False

    article = get_article(int(article_id))
    if not article:
        log.error(f"未找到已入库文章: {keyword} -> #{article_id}")
        return False

    log.info(
        f"🧾 已定位本次文章: #{article['id']} "
        f"{'(更新已有文章)' if save_result.get('action') == 'updated' else '(新建文章)'}"
    )

    passed = quality_loop(article)

    # 质检通过 → 导出 HTML → 自动内链
    if passed:
        # 导出 HTML 到同步目录
        try:
            from core.exporter import WebsiteExporter
            exporter = WebsiteExporter()
            exporter.export_article(article["id"])
        except Exception as e:
            log.error(f"HTML 导出失败: {e}")

        try:
            linker = AutoLinker()
            result = linker.link_article(article["id"])
            log.info(f"🔗 内链: 出链 {result['outgoing']}, 入链 {result['incoming']}")
        except Exception as e:
            log.error(f"内链失败: {e}")

    mark_keyword_done(kw_id, article["id"])
    return passed


def ensure_pending_keywords(agents: GeoAgents, tasks: GeoTasks) -> list:
    """确保有待处理关键词（侦察→种子注入→退出）"""
    pending = get_pending_keywords()
    if pending:
        return pending

    # 尝试侦察
    for i in range(SCOUT_MAX_RETRIES):
        log.info(f"💤 无关键词，侦察第 {i+1}/{SCOUT_MAX_RETRIES} 次...")
        try:
            run_scout(agents, tasks)
            pending = get_pending_keywords()
            if pending:
                return pending
        except Exception as e:
            log.error(f"侦察异常: {e}")
        time.sleep(10 * (i + 1))

    # 尝试种子注入
    log.info("🌱 侦察无果，注入种子关键词...")
    if inject_seed_keywords() > 0:
        return get_pending_keywords()

    return []


def get_total_articles() -> int:
    """查询数据库当前文章总数"""
    cnx = db_manager.get_connection()
    if not cnx:
        return 0
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT COUNT(*) FROM geo_articles")
        return cursor.fetchone()[0] or 0
    finally:
        cursor.close()
        cnx.close()


def get_today_gap_article_count() -> int:
    """统计今天已自动生成的 GEO 真空词文章数"""
    cnx = db_manager.get_connection()
    if not cnx:
        return 0
    try:
        cursor = cnx.cursor()
        cursor.execute(
            "SELECT COUNT(DISTINCT a.id) "
            "FROM geo_articles a "
            "JOIN geo_keywords k ON k.target_article_id = a.id "
            "WHERE k.search_volume >= %s AND DATE(a.created_at) = CURDATE()",
            (GEO_GAP_PRIORITY,),
        )
        result = cursor.fetchone()
        return int(result[0] or 0) if result else 0
    finally:
        cursor.close()
        cnx.close()


def sleep_until_next_gap_window():
    """今日 quota 完成后，休眠到次日 00:05。"""
    now = datetime.now()
    next_run = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    seconds = max(300, int((next_run - now).total_seconds()))
    hours = round(seconds / 3600, 2)
    log.info(f"🌙 今日 GEO 真空词 quota 已完成，休眠至次日窗口（约 {hours}h）")
    time.sleep(seconds)


def run_trend_scout(max_keywords: int = 10) -> list[str]:
    """调用 TrendScout 发现新热词并注入关键词队列，返回新增词列表"""
    try:
        scout = TrendScout(max_keywords=max_keywords)
        new_kws = scout.run()
        return new_kws
    except Exception as e:
        log.error(f"TrendScout 异常: {e}")
        return []


# ═══════════════════════════════════════════
#  主循环
# ═══════════════════════════════════════════

def main():
    """主循环 — 增量热点驱动生产模式"""
    log.info("GEO 知识引擎 v4.0 启动（增量模式）")
    log.info(f"   构建版本: {format_build_label()}")
    if capability_store.ensure_seed_data():
        log.info("   深亚工艺能力仓库: 已就绪")
    else:
        log.warning("   深亚工艺能力仓库: 初始化失败，将回退为本地 JSON 上下文")
    log.info(
        f"   基准文章量: {MAX_ARTICLES} 篇 | "
        f"日真空词产能: {DAILY_GAP_ARTICLES} 篇 | "
        f"{tracker.monthly_summary()}"
    )

    if not check_api_health():
        log.critical("❌ API 连通性检查失败，退出。")
        return

    agents = GeoAgents()
    tasks = GeoTasks()

    total_success, total_failed = 0, 0

    while True:
        gc.collect()

        # ── 120 篇后：切换到 GEO 真空词自动生产模式 ──
        total = get_total_articles()
        if total >= MAX_ARTICLES:
            today_gap_count = get_today_gap_article_count()
            remaining = DAILY_GAP_ARTICLES - today_gap_count
            log.info(
                f"🎯 已有 {total} 篇文章（基准 {MAX_ARTICLES}）。"
                f"进入 GEO 真空词自动生产模式，今日进度 {today_gap_count}/{DAILY_GAP_ARTICLES}。"
            )

            if remaining <= 0:
                sleep_until_next_gap_window()
                continue

            pending_gap = get_pending_gap_keywords(limit=remaining)
            if len(pending_gap) < remaining:
                scout_target = max(remaining * 2, DAILY_GAP_ARTICLES)
                new_kws = run_trend_scout(max_keywords=scout_target)
                if new_kws:
                    log.info(f"🔥 捕获并入库 {len(new_kws)} 个 GEO 真空词。")
                else:
                    log.info("💤 暂未发现新的 GEO 真空词。")
                pending_gap = get_pending_gap_keywords(limit=remaining)

            if not pending_gap:
                log.info(f"💤 当前无可生产的 GEO 真空词，{GAP_MODE_RETRY_SECONDS // 60} 分钟后重试。")
                time.sleep(GAP_MODE_RETRY_SECONDS)
                continue

            for kw in pending_gap[:remaining]:
                success = process_keyword(agents, tasks, kw)
                if success:
                    total_success += 1
                else:
                    total_failed += 1

                log.info(f"累计 | 成功: {total_success} | 失败: {total_failed} | {tracker.monthly_summary()}")
                time.sleep(COOLDOWN_SECONDS)

            continue


        pending = ensure_pending_keywords(agents, tasks)
        if not pending:
            log.error("所有关键词来源耗尽，休眠 5 分钟...")
            time.sleep(300)
            continue

        kw = pending[0]
        success = process_keyword(agents, tasks, kw)

        if success:
            total_success += 1
        else:
            total_failed += 1

        log.info(f"累计 | 成功: {total_success} | 失败: {total_failed} | {tracker.monthly_summary()}")
        time.sleep(COOLDOWN_SECONDS)


if __name__ == "__main__":
    main()
