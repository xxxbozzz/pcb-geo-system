"""
微信公众号发布器 (WeChat MP Publisher)
=====================================
使用微信公众号官方 API 发布文章。
每个注册的公众号都免费有 AppID/AppSecret。

环境变量：
    WECHAT_APP_ID     公众号 AppID
    WECHAT_APP_SECRET 公众号 AppSecret

API 流程：
    1. 获取 access_token（2小时有效）
    2. 上传图文素材（创建草稿）
    3. 发布

参考文档：
    https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html
    https://developers.weixin.qq.com/doc/offiaccount/Publish/Publish.html
"""

import os
import re
import time
import logging
import requests
import markdown

log = logging.getLogger("GEO.WeChat")

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
PUBLISH_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"


class WeChatPublisher:
    """微信公众号发布器（官方 API）"""

    def __init__(self):
        self.app_id = os.getenv("WECHAT_APP_ID", "")
        self.app_secret = os.getenv("WECHAT_APP_SECRET", "")
        self._token = None
        self._token_expires = 0

        if not self.app_id or not self.app_secret:
            log.warning("微信公众号 AppID/AppSecret 未配置，发文功能不可用")

    @property
    def ready(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def _get_token(self) -> str:
        """获取 access_token（带缓存，2小时有效）"""
        now = time.time()
        if self._token and now < self._token_expires:
            return self._token

        resp = requests.get(TOKEN_URL, params={
            "grant_type": "client_credential",
            "appid": self.app_id,
            "secret": self.app_secret,
        })
        data = resp.json()

        if "access_token" in data:
            self._token = data["access_token"]
            self._token_expires = now + data.get("expires_in", 7200) - 60
            log.info("微信 access_token 获取成功")
            return self._token
        else:
            log.error(f"获取 token 失败: {data}")
            raise Exception(f"微信 token 错误: {data.get('errmsg', data)}")

    def _md_to_wechat_html(self, md_text: str) -> str:
        """Markdown → 微信公众号兼容 HTML（移动端优化）"""
        html = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "toc"],
        )

        # 微信图文样式优化
        style_wrapper = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    font-size: 16px; line-height: 1.8; color: #333; padding: 0 8px;">
            {html}
        </div>
        """

        # 替换表格样式（微信不支持 CSS class）
        style_wrapper = style_wrapper.replace(
            "<table>",
            '<table style="width:100%;border-collapse:collapse;font-size:14px;margin:16px 0;">'
        )
        style_wrapper = re.sub(
            r'<t([hd])>',
            r'<t\1 style="border:1px solid #ddd;padding:8px;text-align:left;">',
            style_wrapper,
        )

        # 替换代码块样式
        style_wrapper = style_wrapper.replace(
            "<code>",
            '<code style="background:#f5f5f5;padding:2px 6px;border-radius:3px;font-size:14px;">'
        )

        return style_wrapper

    def publish(self, title: str, content_md: str, author: str = "深亚电子技术团队",
                digest: str = "") -> dict:
        """
        发布文章到微信公众号草稿箱。
        返回 {"success": bool, "media_id": str, "message": str}
        """
        if not self.ready:
            return {"success": False, "media_id": "", "message": "AppID/AppSecret 未配置"}

        try:
            token = self._get_token()

            # 微信要求封面图（thumb_media_id），这里用默认素材
            # 首次使用时需要先上传一张封面图到素材库
            # 暂时跳过封面图（某些公众号类型可以不传）

            html_content = self._md_to_wechat_html(content_md)

            # 摘要：取前 120 字
            if not digest:
                plain = re.sub(r'[#*`\[\]()>|]', '', content_md)
                digest = plain[:120].strip().replace('\n', ' ')

            # 创建草稿
            article_data = {
                "articles": [{
                    "title": title[:64],  # 微信标题上限 64 字
                    "author": author,
                    "digest": digest,
                    "content": html_content,
                    "content_source_url": "https://www.pcbshenya.com",
                    "need_open_comment": 1,
                    # "thumb_media_id": "xxx",  # 封面图素材 ID（必须先上传）
                }]
            }

            resp = requests.post(
                f"{DRAFT_URL}?access_token={token}",
                json=article_data,
            )
            data = resp.json()

            if "media_id" in data:
                media_id = data["media_id"]
                log.info(f"微信草稿创建成功: {media_id}")
                return {
                    "success": True,
                    "media_id": media_id,
                    "message": f"✅ 已保存到微信公众号草稿箱 (media_id: {media_id})",
                }
            else:
                errcode = data.get("errcode", "unknown")
                errmsg = data.get("errmsg", str(data))
                log.error(f"微信草稿创建失败: {errcode} {errmsg}")
                return {
                    "success": False,
                    "media_id": "",
                    "message": f"微信 API 错误 {errcode}: {errmsg}",
                }

        except Exception as e:
            log.error(f"微信发布异常: {e}")
            return {"success": False, "media_id": "", "message": str(e)}

    def publish_and_go_live(self, title: str, content_md: str) -> dict:
        """创建草稿后直接群发（谨慎使用，每天有群发次数限制）"""
        result = self.publish(title, content_md)
        if not result["success"]:
            return result

        try:
            token = self._get_token()
            resp = requests.post(
                f"{PUBLISH_URL}?access_token={token}",
                json={"media_id": result["media_id"]},
            )
            data = resp.json()
            if data.get("errcode") == 0:
                result["message"] = f"✅ 已发布到微信公众号 (publish_id: {data.get('publish_id')})"
            else:
                result["message"] += f" | 群发失败: {data.get('errmsg')}"
        except Exception as e:
            result["message"] += f" | 群发异常: {e}"

        return result
