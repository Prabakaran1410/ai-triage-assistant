"""Vector retrieval over a tenant's knowledge_chunks.

Always goes through tenant_scoped_connection - never a bare connection - so
row-level security is what actually prevents cross-tenant retrieval, not
just this query's WHERE clause.
"""
from dataclasses import dataclass

from sqlalchemy import text

from app.core.db import tenant_scoped_connection
from app.services.embeddings import embed_text


@dataclass
class RetrievedChunk:
    source_id: str
    title: str
    content: str
    updated_at: str
    distance: float


async def retrieve_chunks(tenant_id: str, query: str, k: int = 5) -> list[RetrievedChunk]:
    query_embedding = await embed_text(query, task_type="RETRIEVAL_QUERY")

    async with tenant_scoped_connection(tenant_id) as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    select source_id, title, content, updated_at,
                           embedding <=> (:query_embedding)::vector as distance
                    from knowledge_chunks
                    order by embedding <=> (:query_embedding)::vector
                    limit :k
                    """
                ),
                {"query_embedding": str(query_embedding), "k": k},
            )
        ).fetchall()

    return [
        RetrievedChunk(
            source_id=row.source_id,
            title=row.title,
            content=row.content,
            updated_at=row.updated_at.isoformat(),
            distance=row.distance,
        )
        for row in rows
    ]
