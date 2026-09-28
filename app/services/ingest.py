"""Managing a tenant's knowledge base: the documents replies are grounded in.

Two levels. A *source* is a document somebody added; *chunks* are the
retrievable pieces it was split into. Everything writes both, because a
chunk without its document cannot be shown, re-chunked or deleted as a
unit, and a document without chunks is never retrieved.

Embedding happens before the database is touched. It is the call that fails
- rate limits, an unavailable model - and doing it first means a failure
leaves the existing knowledge base exactly as it was rather than half
replaced.
"""
import datetime as dt
import re
from dataclasses import dataclass

from sqlalchemy import text

from app.core.db import tenant_scoped_connection
from app.services.chunking import chunk_text
from app.services.embeddings import embed_texts


@dataclass(frozen=True)
class KnowledgeChunk:
    source_id: str
    title: str
    content: str
    updated_at: dt.datetime


@dataclass(frozen=True)
class SourceSummary:
    source_id: str
    title: str
    chunk_count: int
    characters: int
    updated_at: str


class IngestError(Exception):
    """A document that cannot be stored as asked."""


def slugify(title: str) -> str:
    """Derive a citation-friendly handle from a title.

    Citations show the source_id, so it should read like something rather
    than a UUID.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:64] or "document"


async def upsert_source(
    tenant_id: str,
    *,
    source_id: str,
    title: str,
    content: str,
    updated_at: dt.datetime | None = None,
) -> int:
    """Add or replace one document. Returns the number of chunks stored.

    Replacing is a delete-then-insert of that source's chunks inside one
    transaction, so a document is never briefly half-indexed while a
    customer's question is being answered against it.
    """
    content = (content or "").strip()
    if not content:
        raise IngestError("A document needs some text.")
    if not (title or "").strip():
        raise IngestError("A document needs a title.")

    pieces = chunk_text(content)
    if not pieces:
        raise IngestError("Nothing could be indexed from that text.")

    embeddings = await embed_texts(pieces)
    when = updated_at or dt.datetime.now(dt.timezone.utc)

    async with tenant_scoped_connection(tenant_id) as conn:
        await conn.execute(
            text(
                "delete from knowledge_chunks "
                "where tenant_id = :tenant_id and source_id = :source_id"
            ),
            {"tenant_id": tenant_id, "source_id": source_id},
        )
        for index, (piece, embedding) in enumerate(zip(pieces, embeddings, strict=True)):
            await conn.execute(
                text(
                    """
                    insert into knowledge_chunks
                        (tenant_id, source_id, title, content, embedding,
                         chunk_index, updated_at)
                    values
                        (:tenant_id, :source_id, :title, :content, (:embedding)::vector,
                         :chunk_index, :updated_at)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "source_id": source_id,
                    "title": title,
                    "content": piece,
                    "embedding": str(embedding),
                    "chunk_index": index,
                    "updated_at": when,
                },
            )
        await conn.execute(
            text(
                """
                insert into knowledge_sources
                    (tenant_id, source_id, title, content, chunk_count, updated_at)
                values
                    (:tenant_id, :source_id, :title, :content, :chunk_count, :updated_at)
                on conflict (tenant_id, source_id) do update set
                    title = excluded.title,
                    content = excluded.content,
                    chunk_count = excluded.chunk_count,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "source_id": source_id,
                "title": title,
                "content": content,
                "chunk_count": len(pieces),
                "updated_at": when,
            },
        )
    return len(pieces)


async def delete_source(tenant_id: str, source_id: str) -> bool:
    """Remove a document and everything retrieved from it. Returns whether
    it existed."""
    async with tenant_scoped_connection(tenant_id) as conn:
        await conn.execute(
            text(
                "delete from knowledge_chunks "
                "where tenant_id = :tenant_id and source_id = :source_id"
            ),
            {"tenant_id": tenant_id, "source_id": source_id},
        )
        result = await conn.execute(
            text(
                "delete from knowledge_sources "
                "where tenant_id = :tenant_id and source_id = :source_id"
            ),
            {"tenant_id": tenant_id, "source_id": source_id},
        )
    return result.rowcount > 0


async def list_sources(tenant_id: str) -> list[SourceSummary]:
    async with tenant_scoped_connection(tenant_id) as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    select source_id, title, chunk_count,
                           length(content) as characters, updated_at
                    from knowledge_sources
                    order by updated_at desc
                    """
                )
            )
        ).fetchall()
    return [
        SourceSummary(
            source_id=r.source_id,
            title=r.title,
            chunk_count=r.chunk_count,
            characters=r.characters,
            updated_at=r.updated_at.isoformat(),
        )
        for r in rows
    ]


async def get_source(tenant_id: str, source_id: str) -> dict | None:
    async with tenant_scoped_connection(tenant_id) as conn:
        row = (
            await conn.execute(
                text(
                    "select source_id, title, content, chunk_count, updated_at "
                    "from knowledge_sources "
                    "where tenant_id = :tenant_id and source_id = :source_id"
                ),
                {"tenant_id": tenant_id, "source_id": source_id},
            )
        ).fetchone()
        if row is None:
            return None
        chunks = (
            await conn.execute(
                text(
                    "select chunk_index, content from knowledge_chunks "
                    "where tenant_id = :tenant_id and source_id = :source_id "
                    "order by chunk_index"
                ),
                {"tenant_id": tenant_id, "source_id": source_id},
            )
        ).fetchall()
    return {
        "source_id": row.source_id,
        "title": row.title,
        "content": row.content,
        "chunk_count": row.chunk_count,
        "updated_at": row.updated_at.isoformat(),
        "chunks": [{"index": c.chunk_index, "content": c.content} for c in chunks],
    }


async def replace_tenant_knowledge(tenant_id: str, chunks: list[KnowledgeChunk]) -> int:
    """Replace a tenant's whole knowledge base in one transaction.

    Used by the evaluation runner, where the corpus is already chunk-sized
    and is reloaded wholesale on every run. Each entry becomes one source
    with one chunk, so the same content is visible in the console.
    """
    embeddings = await embed_texts([c.content for c in chunks])

    async with tenant_scoped_connection(tenant_id) as conn:
        await conn.execute(
            text("delete from knowledge_chunks where tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        await conn.execute(
            text("delete from knowledge_sources where tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            await conn.execute(
                text(
                    """
                    insert into knowledge_chunks
                        (tenant_id, source_id, title, content, embedding,
                         chunk_index, updated_at)
                    values
                        (:tenant_id, :source_id, :title, :content, (:embedding)::vector,
                         0, :updated_at)
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
            await conn.execute(
                text(
                    """
                    insert into knowledge_sources
                        (tenant_id, source_id, title, content, chunk_count, updated_at)
                    values
                        (:tenant_id, :source_id, :title, :content, 1, :updated_at)
                    on conflict (tenant_id, source_id) do update set
                        title = excluded.title,
                        content = excluded.content,
                        chunk_count = 1,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "source_id": chunk.source_id,
                    "title": chunk.title,
                    "content": chunk.content,
                    "updated_at": chunk.updated_at,
                },
            )
    return len(chunks)
