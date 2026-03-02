"""
知乎专栏发布器 (Zhihu Publisher)
================================
使用 Cookie + requests 逆向 API 发布文章到知乎专栏。
比 Playwright 模拟稳定 10x，速度快 10x。

使用前：
    1. 运行 scripts/login_platforms.py --platform zhihu 扫码登录
    2. Cookie 保存在 config/cookies/zhihu.json

API 端点（逆向自知乎 Web）：
    POST   /api/articles/drafts       → 创建草稿
    PATCH  /api/articles/{id}         → 更新草稿内容
    PUT    /api/articles/{id}/publish  → 发布
"""

import json
import os
import re
import logging
import requests
import markdown

log = logging.getLogger("GEO.Zhihu")

COOKIE_FILE = "config/cookies/zhihu.json"
API_BASE = "https://zhuanlan.zhihu.com/api"


class ZhihuPublisher:
    """知乎专栏发布器"""

    def __init__(self, cookie_file: str = COOKIE_FILE):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://zhuanlan.zhihu.com/write",
            "Origin": "https://zhuanlan.zhihu.com",
        })
        self.ready = self._load_cookies(cookie_file)

    def _load_cookies(self, path: str) -> bool:
        if not os.path.exists(path):
            log.warning(f"Cookie 文件不存在: {path}")
            return False
        try:
            with open(path) as f:
                cookies = json.load(f)
            for c in cookies:
                self.session.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain", ".zhihu.com"),
                    path=c.get("path", "/"),
                )
            # 设置 x-xsrftoken（知乎 CSRF 防护必需）
            xsrf = self.session.cookies.get("_xsrf", domain=".zhihu.com")
            if xsrf:
                self.session.headers["x-xsrftoken"] = xsrf
            log.info("知乎 Cookie 加载成功")
            return True
        except Exception as e:
            log.error(f"Cookie 加载失败: {e}")
            return False

    def _md_to_html(self, md_text: str) -> str:
        """Markdown → 知乎兼容 HTML"""
        html = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "toc"],
        )
        # 知乎不支持 <img> 的外部链接，保留文字即可
        html = re.sub(r'<img[^>]*>', '', html)
        return html

    def publish(self, title: str, content_md: str, topic_tags: list = None) -> dict:
        """
        发布文章到知乎专栏。
        返回 {"success": bool, "url": str, "message": str}
        """
        if not self.ready:
            return {"success": False, "url": "", "message": "Cookie 未就绪，请先运行登录脚本"}

        try:
            # 1. 创建草稿
            resp = self.session.post(f"{API_BASE}/articles/drafts", json={})
            if resp.status_code != 200:
                return {"success": False, "url": "", "message": f"创建草稿失败: {resp.status_code} {resp.text[:200]}"}

            draft = resp.json()
            article_id = draft.get("id")
            if not article_id:
                return {"success": False, "url": "", "message": f"草稿 ID 缺失: {draft}"}

            log.info(f"草稿创建成功: {article_id}")

            # 2. 更新草稿内容
            html_content = self._md_to_html(content_md)
            update_data = {
                "title": title[:100],  # 知乎标题上限 100 字
                "content": html_content,
            }
            # 添加话题标签
            if topic_tags:
                update_data["topics"] = [{"name": t} for t in topic_tags[:3]]

            resp = self.session.put(f"{API_BASE}/articles/drafts/{article_id}", json=update_data)
            if resp.status_code not in (200, 204):
                # 尝试备用端点
                resp = self.session.patch(f"{API_BASE}/articles/{article_id}", json=update_data)
            if resp.status_code not in (200, 204):
                return {"success": False, "url": "", "message": f"更新草稿失败: {resp.status_code} {resp.text[:200]}"}

            log.info(f"草稿内容已更新: {title[:30]}...")

            # 3. 发布（先保存草稿不发布，用户确认后再发布）
            # 如果要直接发布，取消下面的注释：
            # resp = self.session.put(f"{API_BASE}/articles/{article_id}/publish", json={"column": None, "commentPermission": "anyone"})

            url = f"https://zhuanlan.zhihu.com/p/{article_id}"
            return {
                "success": True,
                "url": url,
                "article_id": article_id,
                "message": f"已保存为知乎草稿（ID: {article_id}），请在知乎后台确认发布",
            }

        except Exception as e:
            log.error(f"知乎发布异常: {e}")
            return {"success": False, "url": "", "message": str(e)}

    def publish_and_go_live(self, title: str, content_md: str) -> dict:
        """直接发布（不仅保存草稿）"""
        result = self.publish(title, content_md)
        if not result["success"]:
            return result

        article_id = result.get("article_id")
        try:
            resp = self.session.put(
                f"{API_BASE}/articles/{article_id}/publish",
                json={"column": None, "commentPermission": "anyone"},
            )
            if resp.status_code == 200:
                result["message"] = f"✅ 已发布到知乎: {result['url']}"
            else:
                result["message"] = f"草稿已保存但发布失败: {resp.status_code}"
        except Exception as e:
            result["message"] = f"草稿已保存但发布异常: {e}"

        return result
