"""Provider-agnostic classification + drafting.

Design choice that matters: the model is never trusted to write citation
content itself. It only picks *which* of the numbered snippets we handed it
it actually used (by index); the API then builds citations from our own
retrieval results for those indices. An index the model invents that we
didn't send back is dropped, not trusted - see build_citations() in
app/api/triage.py.
"""
from typing import Protocol

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.models.triage import Intent


class LLMTriageOutput(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    used_snippet_indices: list[int] = Field(default_factory=list)
    draft_reply: str


class LLMProvider(Protocol):
    async def classify_and_draft(
        self, message: str, snippets: list[str]
    ) -> LLMTriageOutput: ...


SYSTEM_PROMPT = """You triage customer messages for a support team.

You are given a customer message and a numbered list of knowledge-base
snippets (numbered from 1). Decide the intent, how confident you are that
the drafted reply is fully supported by the snippets, and write a draft
reply.

Rules:
- Only use facts that appear in the numbered snippets. Never state a policy,
  price, or promise that is not written in one of them.
- If the snippets don't contain enough to answer, write a short draft that
  says a team member will follow up, and set confidence low.
- used_snippet_indices must list only the numbers of snippets you actually
  relied on. If you used none, return an empty list.
- confidence reflects how well-supported the draft is by the snippets, not
  how well-written it is.
"""


class GeminiProvider:
    MODEL = "gemini-3-flash-preview"

    def __init__(self) -> None:
        from google import genai

        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")
        self._client = genai.Client(api_key=settings.google_api_key)

    async def classify_and_draft(
        self, message: str, snippets: list[str]
    ) -> LLMTriageOutput:
        from google.genai import types

        numbered = "\n\n".join(f"[{i + 1}] {s}" for i, s in enumerate(snippets))
        prompt = f"{SYSTEM_PROMPT}\n\nSnippets:\n{numbered or '(none provided)'}\n\nCustomer message:\n{message}"

        response = await self._client.aio.models.generate_content(
            model=self.MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LLMTriageOutput,
            ),
        )
        return LLMTriageOutput.model_validate_json(response.text)


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.llm_provider == "gemini":
            _provider = GeminiProvider()
        else:
            raise NotImplementedError(
                f"LLM_PROVIDER={settings.llm_provider!r} has no provider wired up yet"
            )
    return _provider
