#!/usr/bin/env python3
"""
自动发文调度器 (Auto Publisher)
==============================
从数据库读取已通过质检但未发布的文章，自动发布到知乎和微信公众号。

用法:
    DB_HOST=localhost python auto_publish.py           # 发布到草稿箱
    DB_HOST=localhost python auto_publish.py --live     # 直接发布（谨慎）
"""

import os, sys, time, logging, argparse

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("MYSQL_CONNECTOR_PYTHON_TELEMETRY", "0")

from dotenv import load_dotenv
load_dotenv()

import mysql.connector
from core.zhihu_publisher import ZhihuPublisher
from core.wechat_publisher import WeChatPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("Publisher")


def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root_password"),
        database=os.getenv("DB_NAME", "geo_knowledge_engine"),
        connection_timeout=5,
    )


def get_unpublished_articles(limit: int = 5) -> list:
    """获取已通过质检但未外发的文章"""
    cnx = get_db()
    cursor = cnx.cursor(dictionary=True)
    # publish_status: 1=质检通过, 2=已外发
    cursor.execute(
        "SELECT id, title, content_markdown, slug "
        "FROM geo_articles "
        "WHERE publish_status = 1 AND quality_score >= 80 "
        "ORDER BY created_at ASC LIMIT %s",
        (limit,)
    )
    articles = cursor.fetchall()
    cursor.close()
    cnx.close()
    return articles


def mark_published(article_id: int):
    """标记为已外发"""
    cnx = get_db()
    cursor = cnx.cursor()
    cursor.execute("UPDATE geo_articles SET publish_status = 2 WHERE id = %s", (article_id,))
    cnx.commit()
    cursor.close()
    cnx.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="直接发布（不仅保存草稿）")
    parser.add_argument("--limit", type=int, default=3, help="每次最多发布篇数")
    parser.add_argument("--platform", choices=["all", "zhihu", "wechat"], default="all")
    args = parser.parse_args()

    log.info("=" * 50)
    log.info("  自动发文调度器启动")
    log.info(f"  模式: {'直接发布' if args.live else '保存草稿'}")
    log.info(f"  平台: {args.platform}")
    log.info("=" * 50)

    articles = get_unpublished_articles(args.limit)
    if not articles:
        log.info("没有待发布的文章（publish_status=1 且 score≥80）")
        return

    log.info(f"待发布: {len(articles)} 篇")

    # 初始化发布器
    zhihu = ZhihuPublisher() if args.platform in ("all", "zhihu") else None
    wechat = WeChatPublisher() if args.platform in ("all", "wechat") else None

    for i, article in enumerate(articles, 1):
        title = article["title"]
        content = article["content_markdown"]
        log.info(f"\n[{i}/{len(articles)}] {title[:40]}...")

        success_any = False

        # 知乎
        if zhihu and zhihu.ready:
            if args.live:
                result = zhihu.publish_and_go_live(title, content)
            else:
                result = zhihu.publish(title, content, topic_tags=["PCB", "电子制造"])
            log.info(f"  知乎: {result['message']}")
            if result["success"]:
                success_any = True

        # 微信
        if wechat and wechat.ready:
            if args.live:
                result = wechat.publish_and_go_live(title, content)
            else:
                result = wechat.publish(title, content)
            log.info(f"  微信: {result['message']}")
            if result["success"]:
                success_any = True

        # 标记已发布
        if success_any:
            mark_published(article["id"])
            log.info(f"  ✅ 已标记为已外发")

        time.sleep(5)  # 间隔 5 秒

    log.info("\n✅ 发布完成")


if __name__ == "__main__":
    main()
