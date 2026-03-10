"""Article read service."""

from __future__ import annotations

import json
from typing import Any

from backend.app.db.mysql import database
from backend.app.schemas.articles import (
    ArticleDetailItem,
    ArticleDetailPayload,
    ArticleListPayload,
    ArticleSummaryItem,
    ArticleSummaryPayload,
)


def _decode_json(value: Any) -> dict[str, Any] | list[Any] | None:
    if value in (None, "", b""):
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, (dict, list)):
                return loaded
        except Exception:
            return None
    return None


def _map_article_summary(row: dict[str, Any]) -> ArticleSummaryItem:
    return ArticleSummaryItem(
        id=int(row["id"]),
        title=str(row["title"]),
        slug=str(row["slug"]),
        quality_score=int(row.get("quality_score") or 0),
        publish_status=int(row.get("publish_status") or 0),
        dim_subject=row.get("dim_subject"),
        dim_action=row.get("dim_action"),
        dim_attribute=row.get("dim_attribute"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class ArticlesService:
    """Read-only article query service."""

    base_sql = """
        SELECT
            id, title, slug, quality_score, publish_status,
            dim_subject, dim_action, dim_attribute,
            created_at, updated_at
        FROM geo_articles
    """

    def _build_filters(
        self,
        *,
        status: str | None,
        min_score: int,
        query_text: str | None,
    ) -> tuple[str, tuple[Any, ...]]:
        clauses: list[str] = []
        params: list[Any] = []

        if status == "draft":
            clauses.append("publish_status = 0")
        elif status == "approved":
            clauses.append("publish_status = 1")
        elif status == "published":
            clauses.append("publish_status >= 2")

        if min_score > 0:
            clauses.append("quality_score >= %s")
            params.append(min_score)

        if query_text:
            clauses.append("(title LIKE %s OR slug LIKE %s)")
            like_value = f"%{query_text.strip()}%"
            params.extend([like_value, like_value])

        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return where_sql, tuple(params)

    def list_articles(
        self,
        *,
        status: str | None,
        min_score: int,
        query_text: str | None,
        limit: int,
        offset: int,
    ) -> ArticleListPayload:
        try:
            where_sql, params = self._build_filters(
                status=status,
                min_score=min_score,
                query_text=query_text,
            )
            total = int(
                database.fetch_value(
                    f"SELECT COUNT(*) AS value FROM geo_articles{where_sql}",
                    params=params,
                    default=0,
                )
                or 0
            )
            rows = database.fetch_all(
                f"{self.base_sql}{where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                params=(*params, limit, offset),
            )
            return ArticleListPayload(
                items=[_map_article_summary(row) for row in rows],
                total=total,
                limit=limit,
                offset=offset,
                warning=None,
            )
        except Exception as exc:
            return ArticleListPayload(
                items=[],
                total=0,
                limit=limit,
                offset=offset,
                warning=f"articles_unavailable: {exc}",
            )

    def get_summary(self) -> ArticleSummaryPayload:
        try:
            row = database.fetch_one(
                """
                SELECT
                    COUNT(*) AS total_articles,
                    SUM(CASE WHEN publish_status = 0 THEN 1 ELSE 0 END) AS draft_articles,
                    SUM(CASE WHEN publish_status = 1 THEN 1 ELSE 0 END) AS approved_articles,
                    SUM(CASE WHEN publish_status >= 2 THEN 1 ELSE 0 END) AS published_articles,
                    ROUND(AVG(CASE WHEN quality_score > 0 THEN quality_score END), 1) AS average_quality_score
                FROM geo_articles
                """
            ) or {}
            avg_score = row.get("average_quality_score")
            return ArticleSummaryPayload(
                total_articles=int(row.get("total_articles") or 0),
                draft_articles=int(row.get("draft_articles") or 0),
                approved_articles=int(row.get("approved_articles") or 0),
                published_articles=int(row.get("published_articles") or 0),
                average_quality_score=float(avg_score) if avg_score is not None else None,
                warning=None,
            )
        except Exception as exc:
            return ArticleSummaryPayload(
                total_articles=0,
                draft_articles=0,
                approved_articles=0,
                published_articles=0,
                average_quality_score=None,
                warning=f"articles_summary_unavailable: {exc}",
            )

    def get_article_detail(self, article_id: int) -> ArticleDetailPayload:
        try:
            row = database.fetch_one(
                """
                SELECT
                    id, title, slug, meta_json, content_markdown, quality_score, publish_status,
                    dim_subject, dim_action, dim_attribute, created_at, updated_at
                FROM geo_articles
                WHERE id = %s
                """,
                params=(article_id,),
            )
            if not row:
                return ArticleDetailPayload(article=None, warning="article_not_found")

            keywords = database.fetch_all(
                """
                SELECT keyword
                FROM geo_keywords
                WHERE target_article_id = %s
                ORDER BY keyword ASC
                """,
                params=(article_id,),
            )
            link_counts = database.fetch_one(
                """
                SELECT
                    SUM(CASE WHEN source_id = %s THEN 1 ELSE 0 END) AS outgoing_links_count,
                    SUM(CASE WHEN target_id = %s THEN 1 ELSE 0 END) AS incoming_links_count
                FROM geo_links
                WHERE source_id = %s OR target_id = %s
                """,
                params=(article_id, article_id, article_id, article_id),
            ) or {}
            run = database.fetch_one(
                """
                SELECT id, status
                FROM geo_job_runs
                WHERE article_id = %s
                ORDER BY started_at DESC
                LIMIT 1
                """,
                params=(article_id,),
            )
            article = ArticleDetailItem(
                id=int(row["id"]),
                title=str(row["title"]),
                slug=str(row["slug"]),
                quality_score=int(row.get("quality_score") or 0),
                publish_status=int(row.get("publish_status") or 0),
                dim_subject=row.get("dim_subject"),
                dim_action=row.get("dim_action"),
                dim_attribute=row.get("dim_attribute"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                meta_json=_decode_json(row.get("meta_json")),
                content_markdown=row.get("content_markdown"),
                target_keywords=[str(item["keyword"]) for item in keywords],
                outgoing_links_count=int(link_counts.get("outgoing_links_count") or 0),
                incoming_links_count=int(link_counts.get("incoming_links_count") or 0),
                related_run_id=int(run["id"]) if run and run.get("id") is not None else None,
                related_run_status=str(run["status"]) if run and run.get("status") is not None else None,
            )
            return ArticleDetailPayload(article=article, warning=None)
        except Exception as exc:
            return ArticleDetailPayload(article=None, warning=f"article_detail_unavailable: {exc}")


articles_service = ArticlesService()
