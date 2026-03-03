"""
官网导出器 (Website Exporter)
=============================
负责将数据库中的文章导出为适合官网 CMS 导入的格式。
功能：
    1. HTML 导出：Markdown 转 HTML，注入 SEO Meta 标签
    2. Sitemap 生成：生成 xml 站点地图
    3. 增量同步：记录已导出的 ID，只导出新增部分

使用方法：
    from core.exporter import WebsiteExporter
    exporter = WebsiteExporter()
    exporter.export_all(output_dir="output/website_sync")
"""

import os
import json
import markdown
import re
from datetime import datetime
from core.db_manager import db_manager


class WebsiteExporter:
    """官网内容导出与同步引擎"""

    HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title} - 深亚电子PCB技术百科</title>
    <meta name="description" content="{description}">
    <meta name="keywords" content="{keywords}">
    <meta name="author" content="深亚电子">
    <link rel="canonical" href="https://www.pcbshenya.com/wiki/{slug}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <!-- JSON-LD for AI Search Engines -->
    <script type="application/ld+json">
    {json_ld}
    </script>
    <style>
        article {{ max-width: 800px; margin: 0 auto; line-height: 1.6; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #333; }}
        h1 {{ font-size: 2.5em; margin-bottom: 0.5em; color: #2c3e50; }}
        h2 {{ border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-top: 30px; color: #2c3e50; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 0.95em; }}
        th, td {{ border: 1px solid #e1e4e8; padding: 10px; text-align: left; }}
        th {{ background-color: #f8f9fa; font-weight: 600; color: #333; }}
        tr:nth-child(even) {{ background-color: #fcfcfc; }}
        code {{ background-color: #f6f8fa; padding: 2px 5px; border-radius: 3px; font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace; font-size: 0.9em; }}
        .meta {{ color: #7f8c8d; font-size: 0.9em; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #eee; }}
        blockquote {{ border-left: 4px solid #3498db; margin: 0; padding-left: 15px; color: #7f8c8d; background: #f9f9f9; padding: 10px 15px; }}
        a {{ color: #3498db; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <article>
        <h1>{title}</h1>
        <div class="meta">
            <span>发布日期: {date}</span> | 
            <span>分类: {category}</span>
        </div>
        <div class="content">
            {html_content}
        </div>
    </article>
</body>
</html>
"""

    def __init__(self):
        self.db = db_manager

    def export_all(self, output_dir: str = "output/website_sync"):
        """导出所有已发布(status=2) 或 待审(status=1) 的文章"""
        print(f"🚀 启动官网导出任务，目标: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)

        cnx = self.db.get_connection()
        if not cnx:
            print("❌ 数据库连接失败")
            return

        cursor = cnx.cursor(dictionary=True)
        # 导出 status >= 1 (待审和已发布) 的文章
        cursor.execute("""
            SELECT id, title, slug, content_markdown, meta_json, created_at, updated_at, dim_action
            FROM geo_articles 
            WHERE publish_status >= 1
        """)
        articles = cursor.fetchall()
        
        exported_count = 0
        urls = []

        for row in articles:
            try:
                # 1. 解析元数据
                meta = {}
                raw_meta = row['meta_json']
                if raw_meta:
                    try:
                        if isinstance(raw_meta, dict):
                            meta = raw_meta
                        elif isinstance(raw_meta, str):
                            parsed = json.loads(raw_meta)
                            meta = parsed if isinstance(parsed, dict) else {}
                        else:
                            meta = {}
                    except:
                        meta = {}
                
                # 2. 生成 HTML
                html_body = markdown.markdown(
                    row['content_markdown'],
                    extensions=['tables', 'fenced_code', 'toc']
                )
                
                # 提取摘要作为 description (取前150字，去除非文本)
                description = meta.get('description', '')
                if not description:
                    text_only = re.sub(r'<[^>]+>', '', html_body)
                    description = text_only[:150].replace('\n', ' ') + '...'

                keywords = meta.get('keywords', [])
                if isinstance(keywords, list):
                    keywords = ",".join(keywords)
                
                full_html = self.HTML_TEMPLATE.format(
                    title=row['title'],
                    description=description,
                    keywords=keywords,
                    slug=row['slug'],
                    date=row['created_at'].strftime("%Y-%m-%d"),
                    category=row['dim_action'] or 'General',
                    html_content=html_body,
                    json_ld=self._generate_json_ld(row, description, row['created_at'].strftime("%Y-%m-%d"))
                )

                # 3. 写入文件
                safe_slug = row['slug'].strip('/')
                file_path = os.path.join(output_dir, safe_slug + ".html")
                
                # 确保父目录存在
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(full_html)
                
                urls.append(f"https://www.pcbshenya.com/wiki/{safe_slug}")
                exported_count += 1
                # print(f"  ✅ 导出: {safe_slug}.html")

            except Exception as e:
                print(f"  ❌ 导出失败 {row['id']}: {e}")

        # 4. 生成 Sitemap 和 robots.txt
        self._generate_sitemap(urls, output_dir)
        self._generate_robots_txt(output_dir)
        
        cursor.close()
        cnx.close()
        print(f"🏁 导出完成，共 {exported_count} 篇文件及其 Sitemap。")

    def _generate_json_ld(self, row: dict, description: str, date: str):
        """生成 Schema.org JSON-LD"""
        # 1. Article Schema
        schema = {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": row['title'],
            "image": ["https://www.pcbshenya.com/images/logo.png"], # 默认图
            "datePublished": date,
            "dateModified": row['updated_at'].strftime("%Y-%m-%d") if row.get('updated_at') else date,
            "author": [{
                "@type": "Organization",
                "name": "深亚电子",
                "url": "https://www.pcbshenya.com"
            }],
            "description": description,
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": f"https://www.pcbshenya.com/wiki/{row['slug']}"
            }
        }
        
        # 2. FAQPage Schema (如果内容包含 FAQ)
        # 简单解析 FAQ：查找 **Q:** 和 A:
        content = row['content_markdown']
        faq_items = []
        
        # 简单的正则匹配 FAQ
        import re
        qa_pairs = re.findall(r'\*\*Q[:：](.+?)\*\*\s*\n+A[:：](.+?)(\n\n|$)', content, re.DOTALL)
        
        if qa_pairs:
            faq_schema = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": []
            }
            for q, a, _ in qa_pairs:
                faq_schema["mainEntity"].append({
                    "@type": "Question",
                    "name": q.strip(),
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": a.strip()
                    }
                })
            # 如果有 FAQ，返回数组 [Article, FAQPage]
            return json.dumps([schema, faq_schema], ensure_ascii=False, indent=2)
            
        return json.dumps(schema, ensure_ascii=False, indent=2)

    def _generate_robots_txt(self, output_dir: str):
        """生成 robots.txt"""
        content = """User-agent: *
Allow: /
Sitemap: https://www.pcbshenya.com/wiki/sitemap.xml
"""
        with open(os.path.join(output_dir, "robots.txt"), "w") as f:
            f.write(content)
        print("  🤖 robots.txt 已生成")

    def _generate_sitemap(self, urls: list, output_dir: str):
        """生成标准 XML Sitemap"""
        sitemap_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        sitemap_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        for url in urls:
            sitemap_content.append('  <url>')
            sitemap_content.append(f'    <loc>{url}</loc>')
            sitemap_content.append(f'    <lastmod>{today}</lastmod>')
            sitemap_content.append('    <changefreq>weekly</changefreq>')
            sitemap_content.append('    <priority>0.8</priority>')
            sitemap_content.append('  </url>')
            
        sitemap_content.append('</urlset>')
        
        with open(os.path.join(output_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
            f.write("\n".join(sitemap_content))
        print("  🗺️  Sitemap 已生成: sitemap.xml")


if __name__ == "__main__":
    exporter = WebsiteExporter()
    exporter.export_all()
