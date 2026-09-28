"""Schemas for managing the documents replies are grounded in."""
from pydantic import BaseModel, Field


class SourceSummaryModel(BaseModel):
    source_id: str
    title: str
    chunk_count: int
    characters: int
    updated_at: str


class SourceList(BaseModel):
    sources: list[SourceSummaryModel]


class SourceChunk(BaseModel):
    index: int
    content: str


class SourceDetail(BaseModel):
    source_id: str
    title: str
    content: str
    chunk_count: int
    updated_at: str
    # The pieces it was split into, so a reviewer can see what retrieval
    # actually works against rather than guessing from the whole document.
    chunks: list[SourceChunk]


class UpsertSourceRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    # Omitted on create: derived from the title. Supplied to replace an
    # existing document, since citations already point at that handle.
    source_id: str | None = Field(default=None, max_length=64)


class UpsertSourceResponse(BaseModel):
    source_id: str
    chunk_count: int
