"""Knowledge base management against a real database.

The embedding call is stubbed: these test storage, replacement and
isolation, and paying Google to embed "hello" on every run would make them
slow and rate-limited for no added confidence. Chunking and embedding are
covered on their own elsewhere.
"""
import os
import uuid

import pytest
from sqlalchemy import text

from app.core.db import get_engine, tenant_scoped_connection
from app.services import ingest
from app.services.ingest import (
    IngestError,
    delete_source,
    get_source,
    list_sources,
    slugify,
    upsert_source,
)

pytestmark = pytest.mark.skipif(
    "APP_DATABASE_URL" not in os.environ,
    reason="requires a live database; set APP_DATABASE_URL to run",
)

EMBEDDING_DIMENSIONS = 768


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch):
    async def fake_embed_texts(texts, *, task_type="RETRIEVAL_DOCUMENT"):
        return [[0.001] * EMBEDDING_DIMENSIONS for _ in texts]

    monkeypatch.setattr(ingest, "embed_texts", fake_embed_texts)


@pytest.fixture
async def tenant():
    tid = str(uuid.uuid4())
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into tenants (id, name) values (:id, :n)"),
            {"id": tid, "n": f"knowledge-test-{tid}"},
        )
    yield tid
    async with engine.begin() as conn:
        await conn.execute(text("delete from tenants where id = :id"), {"id": tid})


async def test_a_document_is_stored_and_listed(tenant):
    count = await upsert_source(
        tenant,
        source_id="returns",
        title="Returns policy",
        content="Unused items can be returned within 60 days of purchase.",
    )
    assert count == 1

    sources = await list_sources(tenant)
    assert [s.source_id for s in sources] == ["returns"]
    assert sources[0].title == "Returns policy"
    assert sources[0].chunk_count == 1


async def test_a_long_document_is_split_into_several_chunks(tenant):
    long_text = "\n\n".join(
        f"Paragraph {i}. " + "Policy detail that goes on for a while. " * 8
        for i in range(6)
    )
    count = await upsert_source(
        tenant, source_id="handbook", title="Handbook", content=long_text
    )
    assert count > 1

    detail = await get_source(tenant, "handbook")
    assert detail["chunk_count"] == count
    assert len(detail["chunks"]) == count
    # Chunks come back in reading order, not whatever the index returns.
    assert [c["index"] for c in detail["chunks"]] == list(range(count))
    # The original document survives alongside the pieces, so it can be
    # shown back and re-chunked later. Stored stripped, so compare that way.
    assert detail["content"] == long_text.strip()


async def test_replacing_a_document_leaves_no_orphan_chunks(tenant):
    long_text = "\n\n".join(f"Paragraph {i}. " + "detail " * 60 for i in range(6))
    first = await upsert_source(
        tenant, source_id="policy", title="Policy", content=long_text
    )
    assert first > 1

    await upsert_source(
        tenant, source_id="policy", title="Policy (short)", content="Now it is brief."
    )

    async with tenant_scoped_connection(tenant) as conn:
        rows = (
            await conn.execute(
                text("select content from knowledge_chunks where source_id = 'policy'")
            )
        ).fetchall()
    assert len(rows) == 1, "chunks from the previous version were left behind"
    assert rows[0].content == "Now it is brief."

    sources = await list_sources(tenant)
    assert len(sources) == 1 and sources[0].title == "Policy (short)"


async def test_deleting_a_document_removes_its_chunks(tenant):
    await upsert_source(tenant, source_id="temp", title="Temp", content="Some text here.")
    assert await delete_source(tenant, "temp") is True

    assert await list_sources(tenant) == []
    async with tenant_scoped_connection(tenant) as conn:
        remaining = (
            await conn.execute(
                text("select count(*) as n from knowledge_chunks where source_id = 'temp'")
            )
        ).fetchone()
    assert remaining.n == 0, "a deleted document would still be retrievable"


async def test_deleting_something_that_does_not_exist_reports_it(tenant):
    assert await delete_source(tenant, "never-existed") is False


async def test_a_document_needs_text_and_a_title(tenant):
    with pytest.raises(IngestError, match="some text"):
        await upsert_source(tenant, source_id="x", title="Title", content="   ")
    with pytest.raises(IngestError, match="a title"):
        await upsert_source(tenant, source_id="x", title="  ", content="Body text.")


async def test_one_tenant_cannot_see_anothers_documents(tenant):
    await upsert_source(tenant, source_id="secret", title="Secret", content="Confidential.")

    other = str(uuid.uuid4())
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into tenants (id, name) values (:id, :n)"),
            {"id": other, "n": f"other-{other}"},
        )
    try:
        assert await list_sources(other) == []
        assert await get_source(other, "secret") is None
        # Nor can they delete what they cannot see.
        assert await delete_source(other, "secret") is False
        assert len(await list_sources(tenant)) == 1
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("delete from tenants where id = :id"), {"id": other})


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Returns Policy", "returns-policy"),
        ("Shipping & Handling!", "shipping-handling"),
        ("  Trailhead Club  ", "trailhead-club"),
        ("2026 Pricing", "2026-pricing"),
        ("!!!", "document"),
    ],
)
def test_titles_become_readable_handles(title, expected):
    """Citations show the handle, so it should read like something."""
    assert slugify(title) == expected
