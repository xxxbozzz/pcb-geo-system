"""Publication audit endpoints."""

from fastapi import APIRouter, Query

from backend.app.schemas.api import ApiResponse, ok_response
from backend.app.services.publications_service import publications_service


router = APIRouter(prefix="/publications", tags=["publications"])


@router.get("", response_model=ApiResponse)
def list_publications(
    article_id: int | None = Query(default=None, ge=1, description="Filter by article id"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    status: str | None = Query(default=None, description="Filter by publication status"),
    trigger_mode: str | None = Query(default=None, description="Filter by trigger mode"),
    query: str | None = Query(default=None, description="Title, slug, or external id fuzzy search"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse:
    """Return paginated publication audit records."""
    return ok_response(
        message="publications_list_ready",
        data=publications_service.list_publications(
            article_id=article_id,
            platform=platform,
            status=status,
            trigger_mode=trigger_mode,
            query_text=query,
            limit=limit,
            offset=offset,
        ),
    )


@router.get("/{publication_id}", response_model=ApiResponse)
def get_publication_detail(publication_id: int) -> ApiResponse:
    """Return a single publication audit record."""
    return ok_response(
        message="publication_detail_ready",
        data=publications_service.get_publication_detail(publication_id),
    )
