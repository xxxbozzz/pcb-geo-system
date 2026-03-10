"""Article read endpoints."""

from fastapi import APIRouter, Query

from backend.app.schemas.api import ApiResponse, ok_response
from backend.app.services.articles_service import articles_service


router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=ApiResponse)
def list_articles(
    status: str | None = Query(default=None, description="draft / approved / published"),
    min_score: int = Query(default=0, ge=0, le=100),
    query: str | None = Query(default=None, description="Title or slug fuzzy search"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse:
    """Return paginated article list."""
    return ok_response(
        message="articles_list_ready",
        data=articles_service.list_articles(
            status=status,
            min_score=min_score,
            query_text=query,
            limit=limit,
            offset=offset,
        ),
    )


@router.get("/summary", response_model=ApiResponse)
def get_articles_summary() -> ApiResponse:
    """Return aggregate article status counts."""
    return ok_response(
        message="articles_summary_ready",
        data=articles_service.get_summary(),
    )


@router.get("/{article_id}", response_model=ApiResponse)
def get_article_detail(article_id: int) -> ApiResponse:
    """Return single article detail."""
    return ok_response(
        message="article_detail_ready",
        data=articles_service.get_article_detail(article_id),
    )
