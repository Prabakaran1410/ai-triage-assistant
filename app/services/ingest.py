"""Load a tenant's knowledge base: embed each chunk and store it.

`replace_tenant_knowledge` swaps a tenant's whole knowledge base in one
transaction, so a failure midway never leaves half of a knowledge base
behind. Used by the evaluation runner today; the ingestion connectors
planned for Phase 1 (docs, Drive, Confluence) will sit on top of the same
function.
"""
import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text

from app.core.db import tenant_scoped_connection
from app.services.embeddings import embed_texts


@dataclass(frozen=True)
class KnowledgeChunk:
    source_id: str
    title: str
    content: str
    updated_at: dt.datetime


async def replace_tenant_knowledge(tenant_id: str, chunks: list[KnowledgeChunk]) -> int:
    # Embed first: if the embedding call fails we haven't touched the database.
    embeddings = await embed_texts([c.content for c in chunks])

    async with tenant_scoped_connection(tenant_id) as conn:
        await conn.execute(
            text("delete from knowledge_chunks where tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            await conn.execute(
                text(
                    """
                    insert into knowledge_chunks
                        (tenant_id, source_id, title, content, embedding, updated_at)
                    values
                        (:tenant_id, :source_id, :title, :content, (:embedding)::vector, :updated_at)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "source_id": chunk.source_id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "embedding": str(embedding),
                    "updated_at": chunk.updated_at,
                },
            )
    return len(chunks)
