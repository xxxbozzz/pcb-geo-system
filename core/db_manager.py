"""
数据库管理器 (Database Manager)
================================
本模块提供 MySQL 数据库的连接池管理和 CRUD 操作。
负责与 geo_articles / geo_keywords / geo_links 三张核心表交互。

使用方法：
    from core.db_manager import db_manager
    db_manager.save_article({...})
"""

import os
import json
import hashlib

import mysql.connector
from mysql.connector import pooling


class DatabaseManager:
    """知识引擎数据库管理器 — 基于 MySQL 连接池"""

    def __init__(self):
        """初始化连接池，配置从环境变量读取"""
        self.db_config = {
            'user': os.environ.get('DB_USER', 'root'),
            'password': os.environ.get('DB_PASSWORD', 'root_password'),
            'host': os.environ.get('DB_HOST', 'mysql_db'),
            'database': os.environ.get('DB_NAME', 'geo_knowledge_engine'),
            'port': 3306,
            'raise_on_warnings': True,
        }
        try:
            self.pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="geo_pool",
                pool_size=5,
                **self.db_config,
            )
            print("✅ 数据库连接池初始化成功")
        except Exception as e:
            print(f"❌ 数据库连接池初始化失败: {e}")
            self.pool = None

    def get_connection(self):
        """从连接池获取一个连接"""
        if not self.pool:
            return None
        try:
            return self.pool.get_connection()
        except Exception as e:
            print(f"❌ 获取数据库连接失败: {e}")
            return None

    # ──────────────────── 文章操作 ────────────────────

    @staticmethod
    def _calculate_hash(content: str) -> str:
        """计算内容的 MD5 指纹（用于去重）"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def article_exists(self, slug: str) -> bool:
        """检查指定 slug 的文章是否已存在"""
        cnx = self.get_connection()
        if not cnx:
            return False
        cursor = cnx.cursor()
        cursor.execute("SELECT id FROM geo_articles WHERE slug = %s", (slug,))
        result = cursor.fetchone()
        cursor.close()
        cnx.close()
        return result is not None

    def is_duplicate_content(self, content_hash: str) -> bool:
        """检查是否存在内容哈希完全相同的文章"""
        cnx = self.get_connection()
        if not cnx:
            return False
        cursor = cnx.cursor()
        cursor.execute("SELECT id FROM geo_articles WHERE content_hash = %s", (content_hash,))
        result = cursor.fetchone()
        cursor.close()
        cnx.close()
        return result is not None

    def save_article(self, article_data: dict, status: int = 0) -> bool:
        """
        保存文章到数据库

        参数:
            article_data: 包含 title, slug, content, meta, dim_* 的字典
            status: 发布状态 (0=草稿, 1=待审, 2=已发, 3=归档)

        返回:
            是否保存成功
        """
        cnx = self.get_connection()
        if not cnx:
            return False

        try:
            cursor = cnx.cursor()
            content_hash = self._calculate_hash(article_data.get('content', ''))

            # 内容去重检查
            if self.is_duplicate_content(content_hash):
                print(f"⚠️ 检测到重复内容: {article_data.get('title')}，已跳过。")
                cursor.close()
                cnx.close()
                return False

            # 使用 UPSERT：新文章插入，相同 slug 则更新
            query = """
                INSERT INTO geo_articles
                (title, slug, meta_json, content_markdown, content_hash,
                 publish_status, dim_subject, dim_action, dim_attribute)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                title=%s, meta_json=%s, content_markdown=%s,
                content_hash=%s, updated_at=NOW()
            """
            meta_json_str = json.dumps(article_data.get('meta', {}), ensure_ascii=False)

            values = (
                article_data.get('title'),
                article_data.get('slug'),
                meta_json_str,
                article_data.get('content'),
                content_hash,
                status,
                article_data.get('dim_subject'),
                article_data.get('dim_action'),
                article_data.get('dim_attribute'),
                # ON DUPLICATE KEY UPDATE 参数
                article_data.get('title'),
                meta_json_str,
                article_data.get('content'),
                content_hash,
            )

            cursor.execute(query, values)
            cnx.commit()
            print(f"✅ 文章已保存: {article_data.get('title')} (状态: {status})")
            cursor.close()
            cnx.close()
            return True

        except Exception as e:
            print(f"❌ 保存文章失败: {e}")
            if cnx:
                cnx.close()
            return False

    # ──────────────────── 关键词操作 ────────────────────

    def add_keyword(self, keyword: str, search_volume: int = 0, difficulty: int = 0) -> bool:
        """
        添加关键词到策略库（自动忽略已存在的关键词）

        参数:
            keyword: 目标关键词
            search_volume: 月搜索量
            difficulty: SEO 难度 (0-100)
        """
        cnx = self.get_connection()
        if not cnx:
            return False
        try:
            cursor = cnx.cursor()
            cursor.execute(
                "INSERT IGNORE INTO geo_keywords (keyword, search_volume, difficulty) VALUES (%s, %s, %s)",
                (keyword, search_volume, difficulty),
            )
            cnx.commit()
            cursor.close()
            cnx.close()
            return True
        except Exception as e:
            print(f"❌ 添加关键词失败: {e}")
            if cnx:
                cnx.close()
            return False


# 全局单例 — 所有模块共享同一个连接池
db_manager = DatabaseManager()
