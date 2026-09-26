"""Text embeddings, currently Gemini-only.

Kept as its own module (not folded into llm.py) because the embedding model
and the generation model are chosen independently - e.g. Gemini for
generation with a different provider's embeddings is a realistic setup.
"""
from google import genai
from google.genai import types

from app.core.config import get_settings

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")
        _client = genai.Client(api_key=settings.google_api_key)
    return _client


async def embed_text(text: str, *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Embed one piece of text.

    `task_type` matters for retrieval quality: documents are embedded with
    RETRIEVAL_DOCUMENT, queries with RETRIEVAL_QUERY - Gemini's embedding
    model optimizes each differently even though the output shape is the
    same.
    """
    client = _get_client()
    response = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    return response.embeddings[0].values


async def embed_texts(texts: list[str], *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed many texts in one request (used when ingesting a knowledge base)."""
    if not texts:
        return []
    client = _get_client()
    response = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    embeddings = [e.values for e in response.embeddings]
    if len(embeddings) != len(texts):
        raise RuntimeError(f"Asked for {len(texts)} embeddings, got {len(embeddings)}")
    return embeddings
