"""
PCB GEO 知识引擎 — 控制台 v4.0
================================
品牌蓝 + 毛玻璃设计，4 页结构。
"""

import streamlit as st
import pandas as pd
import mysql.connector
import os
import sys
import time
import hashlib
import json
import tempfile

# 确保项目根目录在 sys.path（dashboard 从子目录运行时需要）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dashboard.components import inject_theme, icon, kpi_card, score_tag, status_dot
from dashboard.components import article_row, board_column, sys_info_row, section_header

st.set_page_config(
    page_title="PCB GEO 知识引擎 | 深亚电子",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════
#  数据库
# ═══════════════════════════════════════════

@st.cache_resource(ttl=60)
def get_connection():
    """缓存数据库连接，60秒过期"""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root_password"),
        database=os.getenv("DB_NAME", "geo_knowledge_engine"),
        connection_timeout=5,
        autocommit=True,
    )


def query(sql: str, params=None) -> pd.DataFrame:
    """执行查询，连接断开时自动重连"""
    try:
        cnx = get_connection()
        cnx.ping(reconnect=True)
        return pd.read_sql(sql, cnx, params=params)
    except Exception as e:
        st.cache_resource.clear()
        st.error(f"数据库查询失败: {e}")
        return pd.DataFrame()


def query_value(sql: str, default=0):
    """查询单个值"""
    df = query(sql)
    if df.empty:
        return default
    return df.iloc[0, 0] if df.iloc[0, 0] is not None else default


def execute_sql(sql: str, params=None):
    """执行写操作"""
    try:
        cnx = get_connection()
        cnx.ping(reconnect=True)
        cursor = cnx.cursor()
        cursor.execute(sql, params)
        cnx.commit()
        cursor.close()
        return True
    except Exception as e:
        st.error(f"数据库操作失败: {e}")
        return False


# ═══════════════════════════════════════════
#  注入主题 + 侧边栏
# ═══════════════════════════════════════════

inject_theme()

st.sidebar.markdown(f"""
<div style="padding:12px 0 8px 0;">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
        {icon('layers')}
        <span style="font-size:1.05rem;font-weight:600;color:#f1f3f9 !important;">GEO 控制台</span>
    </div>
    <div style="font-size:0.7rem;color:#545b72 !important;">v4.0 · 深亚电子</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "导航",
    ["总览", "内容管理", "知识图谱", "系统状态"],
    label_visibility="collapsed",
)

if st.sidebar.button("刷新数据"):
    st.cache_resource.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("© 2026 深亚电子 · GEO Engine v4.0")


# ═══════════════════════════════════════════
#  页面 1: 总览
# ═══════════════════════════════════════════

if page == "总览":
    st.markdown('<div class="page-title">数据总览</div>', unsafe_allow_html=True)

    # ── KPI 卡片 ──
    total = query_value("SELECT COUNT(*) FROM geo_articles")
    passed = query_value("SELECT COUNT(*) FROM geo_articles WHERE publish_status >= 1")
    pending_kw = query_value("SELECT COUNT(*) FROM geo_keywords WHERE target_article_id IS NULL")
    avg_score = query_value("SELECT ROUND(AVG(quality_score),1) FROM geo_articles WHERE quality_score > 0")
    links = query_value("SELECT COUNT(*) FROM geo_links")

    st.markdown('<div class="kpi-row">', unsafe_allow_html=True)
    cols = st.columns(5)
    kpi_data = [
        ("file-text", total, "文章总数"),
        ("check-circle", passed, "质检通过"),
        ("clock", pending_kw, "待处理词"),
        ("target", avg_score, "平均质量分"),
        ("link", links, "内链关系"),
    ]
    for col, (ic, val, label) in zip(cols, kpi_data):
        with col:
            kpi_card(ic, val, label)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 7日趋势图 & 发文统计 ──
    st.markdown('<div class="grid-2-1">', unsafe_allow_html=True)
    col_chart, col_board = st.columns([3, 2], gap="large")

    with col_chart:
        st.markdown(f'<div class="sub-title">{icon("trending-up")} 7日产出趋势</div>', unsafe_allow_html=True)

        trend_df = query("""
            SELECT DATE(created_at) as day, COUNT(*) as count
            FROM geo_articles
            WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY DATE(created_at)
            ORDER BY day
        """)

        if not trend_df.empty:
            import plotly.graph_objects as go

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=trend_df["day"],
                y=trend_df["count"],
                mode="lines+markers",
                line=dict(color="#3b82f6", width=2.5),
                marker=dict(size=7, color="#2563eb"),
                fill="tozeroy",
                fillcolor="rgba(37, 99, 235, 0.08)",
                hovertemplate="%{x|%m-%d}<br>产出 %{y} 篇<extra></extra>",
            ))
            fig.update_layout(
                height=260,
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(
                    showgrid=False,
                    color="#545b72",
                    tickformat="%m-%d",
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor="rgba(255,255,255,0.04)",
                    color="#545b72",
                    dtick=1,
                ),
                font=dict(family="Inter, sans-serif", size=12),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("暂无近7日数据。")

        # ── 发文统计 ──
        st.markdown(f'<div class="sub-title" style="margin-top:24px;">{icon("bar-chart")} 发文统计</div>', unsafe_allow_html=True)
        stats_df = query("""
            SELECT
                SUM(CASE WHEN publish_status = 0 THEN 1 ELSE 0 END) as drafts,
                SUM(CASE WHEN publish_status = 1 THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN publish_status >= 2 THEN 1 ELSE 0 END) as published
            FROM geo_articles
        """)
        if not stats_df.empty:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("草稿", int(stats_df.iloc[0]["drafts"] or 0))
            with c2:
                st.metric("质检通过", int(stats_df.iloc[0]["approved"] or 0))
            with c3:
                st.metric("已发布", int(stats_df.iloc[0]["published"] or 0))

    # ── 生产看板 ──
    with col_board:
        st.markdown(f'<div class="sub-title">{icon("layout")} 生产看板</div>', unsafe_allow_html=True)

        pending = query(
            "SELECT keyword FROM geo_keywords WHERE target_article_id IS NULL ORDER BY id ASC LIMIT 5"
        )
        drafts = query(
            "SELECT title FROM geo_articles WHERE publish_status = 0 ORDER BY created_at DESC LIMIT 5"
        )
        done = query(
            "SELECT title FROM geo_articles WHERE publish_status >= 1 ORDER BY created_at DESC LIMIT 5"
        )

        board_column("clock", "待处理词", [r["keyword"] for _, r in pending.iterrows()])
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        board_column("wrench", "质检与修复", [
            (str(r["title"])[:22] + "..." if len(str(r["title"])) > 22 else r["title"])
            for _, r in drafts.iterrows()
        ])
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        board_column("check-circle", "最新入库", [
            (str(r["title"])[:22] + "..." if len(str(r["title"])) > 22 else r["title"])
            for _, r in done.iterrows()
        ])

    st.markdown('</div>', unsafe_allow_html=True)

    # ── 最新文章 ──
    st.markdown(f'<div class="sub-title" style="margin-top:24px;">{icon("file-text")} 最新入库记录</div>', unsafe_allow_html=True)

    recent = query(
        "SELECT id, title, quality_score, publish_status, created_at "
        "FROM geo_articles ORDER BY created_at DESC LIMIT 8"
    )
    if not recent.empty:
        rows_html = ""
        for _, r in recent.iterrows():
            score = r["quality_score"] or 0
            title = str(r["title"])[:50] + "..." if len(str(r["title"])) > 50 else r["title"]
            date_str = str(r["created_at"])[:16] if r["created_at"] else ""
            rows_html += article_row(title, int(score), int(r["publish_status"]), date_str)
        st.markdown(rows_html, unsafe_allow_html=True)
    else:
        st.info("暂无文章。")


# ═══════════════════════════════════════════
#  页面 2: 内容管理
# ═══════════════════════════════════════════

elif page == "内容管理":
    st.markdown('<div class="page-title">内容管理</div>', unsafe_allow_html=True)

    # ── 筛选栏 ──
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title" style="margin-top:0;">{icon("search")} 筛选条件</div>', unsafe_allow_html=True)
    
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    with col_f1:
        status_filter = st.selectbox("状态", ["全部", "草稿", "已通过", "已发布"], label_visibility="collapsed")
    with col_f2:
        score_filter = st.slider("最低分数", 0, 100, 0, label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

    articles = query(
        "SELECT id, title, quality_score, publish_status, created_at "
        "FROM geo_articles ORDER BY created_at DESC"
    )

    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title" style="margin-top:0;">{icon("database")} 文章列表</div>', unsafe_allow_html=True)

    if articles.empty:
        st.info("暂无文章。")
    else:
        filtered = articles.copy()
        if status_filter == "草稿":
            filtered = filtered[filtered["publish_status"] == 0]
        elif status_filter == "已通过":
            filtered = filtered[filtered["publish_status"] == 1]
        elif status_filter == "已发布":
            filtered = filtered[filtered["publish_status"] >= 2]
        if score_filter > 0:
            filtered = filtered[filtered["quality_score"] >= score_filter]

        st.dataframe(
            filtered[["id", "title", "quality_score", "publish_status", "created_at"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": "ID",
                "title": "标题",
                "quality_score": st.column_config.ProgressColumn("质量分", min_value=0, max_value=100, format="%d"),
                "publish_status": "状态",
                "created_at": "创建时间",
            },
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 文章操作区 ──
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title" style="margin-top:0;">{icon("wrench")} 文章操作</div>', unsafe_allow_html=True)

    col_id, col_btn1, col_btn2, col_btn3, col_btn4 = st.columns([1.5, 1, 1, 1, 1])
    
    with col_id:
        article_id = st.number_input("输入文章 ID", min_value=1, step=1, label_visibility="collapsed")

    with col_btn1:
        if st.button("预览全文", use_container_width=True):
            st.session_state["action"] = "preview"
            st.session_state["action_id"] = int(article_id)

    with col_btn2:
        if st.button("重新修复", use_container_width=True):
            st.session_state["action"] = "refix"
            st.session_state["action_id"] = int(article_id)

    with col_btn3:
        if st.button("回收关键词", use_container_width=True):
            st.session_state["action"] = "recycle"
            st.session_state["action_id"] = int(article_id)

    with col_btn4:
        if st.button("手动发布", use_container_width=True):
            st.session_state["action"] = "publish"
            st.session_state["action_id"] = int(article_id)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── 执行操作 ──
    action = st.session_state.get("action")
    action_id = st.session_state.get("action_id")

    if action and action_id:

        # 预览全文
        if action == "preview":
            st.markdown('<div class="glass-panel" style="border-color:var(--brand-glow);">', unsafe_allow_html=True)
            st.markdown(f'<div class="sub-title" style="margin-top:0;color:var(--brand-light);">{icon("eye")} 文章预览 (ID: {action_id})</div>', unsafe_allow_html=True)
            detail = query(
                f"SELECT title, content_markdown, quality_score, publish_status "
                f"FROM geo_articles WHERE id = {int(action_id)}"
            )
            if not detail.empty:
                row = detail.iloc[0]
                score = int(row["quality_score"] or 0)
                st.markdown(f"""
                <div class="glass-panel">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                        <h2 style="margin:0 !important;">{row['title']}</h2>
                        {score_tag(score)}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                with st.expander("全文内容", expanded=True):
                    st.markdown(row["content_markdown"] or "（空）")
            else:
                st.warning("未找到该文章。")

        # 重新修复
        elif action == "refix":
            detail = query(
                f"SELECT id, title, content_markdown, quality_score "
                f"FROM geo_articles WHERE id = {int(action_id)}"
            )
            if detail.empty:
                st.warning("未找到该文章。")
            else:
                row = detail.iloc[0]
                st.info(f"正在修复: {row['title']}")

                with st.spinner("AutoFixer 正在重写..."):
                    try:
                        from core.auto_fixer import AutoFixer
                        from core.quality_checker import QualityChecker

                        checker = QualityChecker()
                        fixer = AutoFixer()

                        title = row["title"] or ""
                        content = row["content_markdown"] or ""
                        score, report = checker.evaluate_article(title, content)

                        fix_prompt = fixer.generate_fix_prompt(content, report)
                        if not fix_prompt:
                            st.success(f"文章已通过质检 ({score}分)，无需修复。")
                        else:
                            # 调用 LLM 执行返修
                            from dotenv import load_dotenv
                            load_dotenv()
                            os.environ.setdefault("OTEL_SDK_DISABLED", "true")
                            from langchain_openai import ChatOpenAI

                            llm = ChatOpenAI(
                                model="deepseek-chat",
                                openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
                                openai_api_base="https://api.deepseek.com",
                                temperature=0.3,
                                max_tokens=8000,
                            )
                            result = llm.invoke(fix_prompt)
                            new_content = result.content if hasattr(result, "content") else str(result)

                            if len(new_content.strip()) < 500:
                                st.error("返修结果过短，请重试。")
                            else:
                                # 重新质检
                                new_score, new_report = checker.evaluate_article(title, new_content)
                                content_hash = hashlib.md5(new_content.encode("utf-8")).hexdigest()

                                if new_score >= 80:
                                    execute_sql(
                                        "UPDATE geo_articles SET content_markdown=%s, content_hash=%s, "
                                        "quality_score=%s, publish_status=1 WHERE id=%s",
                                        (new_content, content_hash, new_score, int(action_id)),
                                    )
                                    st.success(f"修复成功！新质量分: {new_score} (已通过)")
                                else:
                                    # <80分: 回收关键词 + 删文章
                                    slug = query_value(
                                        f"SELECT slug FROM geo_articles WHERE id = {int(action_id)}",
                                        default="",
                                    )
                                    keyword = str(slug).replace("-", " ").strip()
                                    if keyword:
                                        execute_sql(
                                            "INSERT IGNORE INTO geo_keywords (keyword) VALUES (%s)",
                                            (keyword,),
                                        )
                                    execute_sql(
                                        "DELETE FROM geo_articles WHERE id = %s",
                                        (int(action_id),),
                                    )
                                    st.warning(
                                        f"修复后仍仅 {new_score} 分 (<80)。"
                                        f"已回收关键词「{keyword}」并删除文章，等待重新生成。"
                                    )
                    except Exception as e:
                        st.error(f"修复失败: {e}")

            st.session_state["action"] = None

        # 回收关键词
        elif action == "recycle":
            detail = query(
                f"SELECT id, title, slug FROM geo_articles WHERE id = {int(action_id)}"
            )
            if detail.empty:
                st.warning("未找到该文章。")
            else:
                row = detail.iloc[0]
                keyword = str(row["slug"]).replace("-", " ").strip()
                if keyword:
                    execute_sql(
                        "INSERT IGNORE INTO geo_keywords (keyword) VALUES (%s)",
                        (keyword,),
                    )
                # 解绑关键词引用
                execute_sql(
                    "UPDATE geo_keywords SET target_article_id = NULL WHERE target_article_id = %s",
                    (int(action_id),),
                )
                # 删除内链
                execute_sql(
                    "DELETE FROM geo_links WHERE source_id = %s OR target_id = %s",
                    (int(action_id), int(action_id)),
                )
                # 删除文章
                execute_sql("DELETE FROM geo_articles WHERE id = %s", (int(action_id),))
                st.success(f"已回收关键词「{keyword}」并删除文章 #{action_id}。")

            st.session_state["action"] = None

        # 手动发布 → 选择平台 → 自动推送
        elif action == "publish":
            detail = query(
                f"SELECT id, title, content_markdown, quality_score, publish_status "
                f"FROM geo_articles WHERE id = {int(action_id)}"
            )
            if detail.empty:
                st.warning("未找到该文章。")
                st.session_state["action"] = None
            else:
                row = detail.iloc[0]
                score = int(row["quality_score"] or 0)
                title = str(row["title"])

                st.markdown('<div class="glass-panel" style="border-color:var(--brand-glow);">', unsafe_allow_html=True)
                st.markdown(f'<div class="sub-title" style="margin-top:0;color:var(--brand-light);">{icon("send")} 发布文章 (ID: {action_id})</div>', unsafe_allow_html=True)

                # 文章信息展示
                st.markdown(f"""
                <div style="padding:12px 16px;background:rgba(37,99,235,0.06);border-radius:8px;margin-bottom:16px;">
                    <div style="font-size:1rem;font-weight:600;color:var(--text-primary);margin-bottom:4px;">{title[:60]}</div>
                    <div style="font-size:0.8rem;color:var(--text-secondary);">
                        质量分: {score_tag(score)} &nbsp;|&nbsp; 状态: {'已通过' if row['publish_status'] == 1 else '草稿' if row['publish_status'] == 0 else '已发布'}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # 平台选择
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    pub_zhihu = st.checkbox("📘 知乎专栏", value=True, key="pub_zhihu")
                with col_p2:
                    pub_wechat = st.checkbox("💚 微信公众号", value=True, key="pub_wechat")

                # 模式选择
                pub_mode = st.radio(
                    "发布模式",
                    ["保存到草稿箱（推荐）", "直接发布（立即上线）"],
                    horizontal=True,
                    key="pub_mode",
                )
                is_live = "直接" in pub_mode

                if is_live:
                    st.warning("⚠️ 直接发布后文章会立即上线，微信公众号每天仅可群发 1 次。")

                # 确认发布按钮
                col_confirm, col_cancel = st.columns(2)
                with col_confirm:
                    confirm = st.button("✅ 确认发布", use_container_width=True, type="primary")
                with col_cancel:
                    cancel = st.button("取消", use_container_width=True)

                if cancel:
                    st.session_state["action"] = None
                    st.rerun()

                if confirm:
                    if not pub_zhihu and not pub_wechat:
                        st.error("请至少选择一个发布平台。")
                    else:
                        content_md = row["content_markdown"] or ""
                        results = []

                        with st.spinner("正在推送文章..."):
                            # ── 知乎 ──
                            if pub_zhihu:
                                try:
                                    from core.zhihu_publisher import ZhihuPublisher
                                    zhihu = ZhihuPublisher()
                                    if not zhihu.ready:
                                        results.append(("知乎", False, "Cookie 未就绪，请先运行登录脚本"))
                                    else:
                                        if is_live:
                                            r = zhihu.publish_and_go_live(title, content_md)
                                        else:
                                            r = zhihu.publish(title, content_md, topic_tags=["PCB", "电子制造"])
                                        results.append(("知乎", r["success"], r["message"]))
                                except Exception as e:
                                    results.append(("知乎", False, f"异常: {e}"))

                            # ── 微信 ──
                            if pub_wechat:
                                try:
                                    from core.wechat_publisher import WeChatPublisher
                                    wechat = WeChatPublisher()
                                    if not wechat.ready:
                                        results.append(("微信", False, "AppID/AppSecret 未配置"))
                                    else:
                                        if is_live:
                                            r = wechat.publish_and_go_live(title, content_md)
                                        else:
                                            r = wechat.publish(title, content_md)
                                        results.append(("微信", r["success"], r["message"]))
                                except Exception as e:
                                    results.append(("微信", False, f"异常: {e}"))

                        # ── 显示结果 ──
                        any_success = False
                        for platform, success, msg in results:
                            if success:
                                st.success(f"**{platform}**: {msg}")
                                any_success = True
                            else:
                                st.error(f"**{platform}**: {msg}")

                        # 更新数据库状态
                        if any_success:
                            execute_sql(
                                "UPDATE geo_articles SET publish_status = 2 WHERE id = %s",
                                (int(action_id),),
                            )

                        st.session_state["action"] = None

                st.markdown('</div>', unsafe_allow_html=True)


    # ── GEO 真空词发现 & 手动生产 ──
    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title" style="margin-top:0;">{icon("target")} GEO 真空词发现</div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="color:var(--text-secondary);font-size:0.85rem;margin-bottom:12px;">'
        '发现 AI 搜索引擎回答薄弱的关键词，筛选后手动触发文章生产。</p>',
        unsafe_allow_html=True,
    )

    # 发现按钮
    if st.button("🔍 发现 5 个真空词", use_container_width=True, key="discover_gap"):
        with st.spinner("正在搜索 GEO 真空词..."):
            try:
                from core.trend_scout import TrendScout
                scout = TrendScout(max_keywords=5)
                new_kws = scout.run()
                if new_kws:
                    st.success(f"发现 {len(new_kws)} 个真空词并已入库")
                    st.rerun()
                else:
                    st.warning("暂未发现新的真空词")
            except Exception as e:
                st.error(f"发现失败: {e}")

    # 展示待选关键词（未绑定文章的前 5 个）
    pending_kws = query(
        "SELECT id, keyword, created_at FROM geo_keywords "
        "WHERE target_article_id IS NULL ORDER BY created_at DESC LIMIT 5"
    )

    if not pending_kws.empty:
        st.markdown(
            '<p style="color:var(--text-secondary);font-size:0.85rem;margin-top:16px;margin-bottom:8px;">'
            f'待筛选关键词（{len(pending_kws)} 个）：</p>',
            unsafe_allow_html=True,
        )
        for _, kw_row in pending_kws.iterrows():
            kw_id = int(kw_row["id"])
            kw_text = kw_row["keyword"]

            col_kw, col_produce, col_skip = st.columns([4, 1, 1])
            with col_kw:
                st.markdown(
                    f'<div style="padding:8px 0;color:var(--text-primary);font-size:0.95rem;">'
                    f'🎯 {kw_text}</div>',
                    unsafe_allow_html=True,
                )
            with col_produce:
                if st.button("生产", key=f"produce_{kw_id}", type="primary"):
                    with st.spinner(f"正在生产「{kw_text}」..."):
                        try:
                            import subprocess, sys
                            result = subprocess.run(
                                [sys.executable, "-u", "-c",
                                 f"""
import os, sys
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("MYSQL_CONNECTOR_PYTHON_TELEMETRY", "0")
from dotenv import load_dotenv
load_dotenv()
os.environ["OPENAI_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")
os.environ["OPENAI_API_BASE"] = "https://api.deepseek.com"
os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com"
from batch_generator import process_keyword, GeoAgents, GeoTasks
from langchain_openai import ChatOpenAI
agents = GeoAgents()
tasks = GeoTasks()
kw_row = {{"id": {kw_id}, "keyword": "{kw_text}"}}
success = process_keyword(agents, tasks, kw_row)
print("SUCCESS" if success else "FAILED")
"""],
                                capture_output=True, text=True, timeout=600,
                                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            )
                            if "SUCCESS" in result.stdout:
                                st.success(f"✅ 「{kw_text}」生产完成！")
                            else:
                                st.error(f"生产失败: {result.stderr[-300:] if result.stderr else '未知错误'}")
                        except subprocess.TimeoutExpired:
                            st.error("生产超时（10分钟），请到日志查看进度")
                        except Exception as e:
                            st.error(f"生产异常: {e}")
                    st.rerun()
            with col_skip:
                if st.button("跳过", key=f"skip_{kw_id}"):
                    # 标记为已跳过（设 target_article_id = -1）
                    execute_sql(
                        "UPDATE geo_keywords SET target_article_id = -1 WHERE id = %s",
                        (kw_id,),
                    )
                    st.rerun()
    else:
        st.info("暂无待筛选的真空词，点击上方按钮发现新词。")

    st.markdown('</div>', unsafe_allow_html=True)



# ═══════════════════════════════════════════
#  页面 3: 知识图谱
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
#  页面 3: 知识图谱
# ═══════════════════════════════════════════

elif page == "知识图谱":
    st.markdown('<div class="page-title">知识图谱</div>', unsafe_allow_html=True)

    link_count = query_value("SELECT COUNT(*) FROM geo_links")
    article_count = query_value(
        "SELECT COUNT(DISTINCT id) FROM geo_articles WHERE id IN "
        "(SELECT source_id FROM geo_links UNION SELECT target_id FROM geo_links)"
    )

    st.markdown('<div class="grid-2">', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        kpi_card("link", link_count, "内链总数")
    with c2:
        kpi_card("network", article_count, "关联文章数")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="glass-panel" style="margin-top:24px;">', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title" style="margin-top:0;">{icon("network")} 交互式网络图</div>', unsafe_allow_html=True)

    links_df = query("""
        SELECT l.source_id, l.target_id, l.anchor_text,
               a1.title as source_title, a2.title as target_title
        FROM geo_links l
        JOIN geo_articles a1 ON l.source_id = a1.id
        JOIN geo_articles a2 ON l.target_id = a2.id
        ORDER BY l.created_at DESC LIMIT 200
    """)

    if not links_df.empty:
        try:
            from pyvis.network import Network
            import tempfile
            import streamlit.components.v1 as components

            net = Network(
                height="540px",
                width="100%",
                bgcolor="transparent",
                font_color="#f1f3f9",
                directed=True,
                notebook=False,
                cdn_resources="remote",
            )
            net.set_options("""
            {
                "nodes": {
                    "shape": "dot",
                    "size": 14,
                    "font": {"size": 11, "color": "#8b92a8", "face": "Inter, sans-serif"},
                    "color": {
                        "background": "#2563eb",
                        "border": "rgba(255, 255, 255, 0.1)",
                        "highlight": {"background": "#3b82f6", "border": "#ffffff"}
                    }
                },
                "edges": {
                    "color": {"color": "rgba(255, 255, 255, 0.1)", "highlight": "#2563eb"},
                    "width": 1,
                    "smooth": {"type": "continuous"}
                },
                "physics": {
                    "barnesHut": {
                        "gravitationalConstant": -4000,
                        "centralGravity": 0.3,
                        "springLength": 100,
                        "springConstant": 0.04
                    }
                }
            }
            """)

            added_nodes = set()
            for _, r in links_df.iterrows():
                sid, tid = r["source_id"], r["target_id"]
                n1, n2 = str(r["source_title"])[:20], str(r["target_title"])[:20]

                if sid not in added_nodes:
                    net.add_node(sid, label=n1, title=r["source_title"])
                    added_nodes.add(sid)
                if tid not in added_nodes:
                    net.add_node(tid, label=n2, title=r["target_title"])
                    added_nodes.add(tid)
                net.add_edge(sid, tid, title=f"锚文本: {r['anchor_text']}")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
                net.save_graph(tmp.name)
                with open(tmp.name, "r", encoding="utf-8") as f:
                    html_data = f.read()

            components.html(html_data, height=560)
            os.unlink(tmp.name)

        except ImportError:
            st.warning("请安装 pyvis: `pip install pyvis` 以显示交互式图谱。")
            st.dataframe(links_df)
    else:
        st.info("暂无足够的内链关系数据。")
        
    st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════
#  页面 4: 系统状态
# ═══════════════════════════════════════════

elif page == "系统状态":
    st.markdown('<div class="page-title">系统状态</div>', unsafe_allow_html=True)

    st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-title" style="margin-top:0;">{icon("server")} 服务状态检查</div>', unsafe_allow_html=True)

    try:
        query_value("SELECT 1")
        db_status = '<span style="color:var(--ok-color);font-weight:600;">正常</span>'
    except:
        db_status = '<span style="color:var(--err-color);font-weight:600;">异常</span>'
        
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    api_status = '<span style="color:var(--ok-color);font-weight:600;">已配置</span>' if api_key.startswith("sk-") else '<span style="color:var(--warn-color);font-weight:600;">未配置</span>'

    env_str = os.getenv("APP_ENV", "Production")

    from core.budget import tracker
    budget_stats = tracker.monthly_summary()
    
    rows = [
        sys_info_row("database", "MySQL 数据库连接", db_status),
        sys_info_row("cpu", "DeepSeek API 状态", api_status),
        sys_info_row("layers", "当前运行环境", env_str),
        sys_info_row("clock", "Token 用量统计", f'<span style="color:var(--brand-light);">{budget_stats}</span>'),
    ]
    st.markdown("".join(rows), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown(f'<div class="sub-title" style="margin-top:24px;">{icon("shield")} AI 知识覆盖率检测 (GEO)</div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="glass-panel">
        <p style="color:var(--text-secondary);font-size:0.9rem;margin-bottom:12px;">实时追踪大型语言模型 (LLM) 对深亚电子 PCB 知识的回答覆盖率。由于转入按需生成模式，系统主要通过以下方式扩展知识库：</p>
        <div style="font-size:0.85rem;color:var(--text-primary);display:flex;flex-direction:column;gap:8px;">
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="color:var(--brand-light);">✓</span> 挖掘用户真实痛点和行业高频长尾词
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="color:var(--brand-light);">✓</span> 识别各大平台（DeepSeek / 豆包 / 文心一言等）的回答空白
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="color:var(--brand-light);">✓</span> 优先生成当前模型答不好的技术长文和问答
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
