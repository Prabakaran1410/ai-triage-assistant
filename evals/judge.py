"""LLM-as-judge for answer quality.

Two yes/no questions per drafted reply, chosen because they are what RAG
evaluations (e.g. RAGAS) call faithfulness and answer correctness:

- faithful: is every factual claim in the draft supported by the sources it
  cited? (Polite filler is fine; an invented policy or number is not.)
- correct: does the draft convey the key facts of the reference answer,
  without contradicting it?

Implemented directly instead of via the RAGAS package: RAGAS pulls in
LangChain and needs its own LLM/embedding wiring, while this reuses the
product's provider and model-fallback chain. The metric definitions are the
same; swapping RAGAS in later is a scoring change, not an architecture one.

The judge is itself an LLM, so its verdicts carry some noise. It is a fixed
prompt run over a fixed dataset, which makes run-to-run *comparison* meaningful
even though a single verdict is not gospel.
"""
from pydantic import BaseModel

from app.services.llm import GeminiProvider, get_llm_provider


class JudgeVerdict(BaseModel):
    faithful: bool
    correct: bool
    note: str


JUDGE_PROMPT = """You are grading a draft reply written by a customer-support assistant.

Customer message:
{message}

Draft reply:
{draft}

Sources the draft cited (verbatim):
{sources}

Reference answer (what a correct reply must convey):
{reference}

Decide two things:
- faithful: true only if EVERY factual claim in the draft (numbers, durations,
  prices, policies, conditions) is supported by the cited sources. Polite
  wording and offers to follow up are fine. Any claim not found in the
  sources makes this false.
- correct: true only if the draft conveys the key facts of the reference
  answer and does not contradict it.
Then give a one-sentence note explaining any false verdict.
"""


async def judge(message: str, draft: str, sources: list[str], reference: str) -> JudgeVerdict:
    provider = get_llm_provider()
    if not isinstance(provider, GeminiProvider):
        raise NotImplementedError("The judge currently needs the Gemini provider")
    prompt = JUDGE_PROMPT.format(
        message=message,
        draft=draft,
        sources="\n".join(f"- {s}" for s in sources) or "(none)",
        reference=reference,
    )
    verdict, _model = await provider.generate_structured(
        prompt, JudgeVerdict, name="eval-judge"
    )
    return verdict
