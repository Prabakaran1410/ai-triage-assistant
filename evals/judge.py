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

Known false-positive mode: the judge intermittently marks a draft unfaithful
for promising that a team member will follow up, even though GROUNDING_RULES
says explicitly that deferral is not a factual claim. Two attempts at
wording the rule harder did not stop it. Faithfulness therefore tends to sit
at ~98% rather than 100% even when no draft actually fabricates anything;
check the flagged row before treating a dip as a real regression. Left as a
documented artifact rather than tuned away, because rewriting the judge until
the number looks right is how an eval stops meaning anything.

The judge is itself an LLM, so its verdicts carry some noise. It is a fixed
prompt run over a fixed dataset, which makes run-to-run *comparison* meaningful
even though a single verdict is not gospel.
"""
from pydantic import BaseModel

from app.services.llm import GeminiProvider, get_llm_provider


class JudgeVerdict(BaseModel):
    faithful: bool
    correct: bool | None = None
    note: str


class FaithfulnessVerdict(BaseModel):
    """Used when there is no reference answer. Faithfulness only needs the
    draft and the sources it cited, so it applies to every drafted reply -
    including escalated ones, where a hallucinated draft still reaches a
    reviewer who may rubber-stamp it."""

    faithful: bool
    note: str


GROUNDING_RULES = """
- faithful is false if the draft states ANY fact not present in the cited
  sources - including a reasonable-sounding inference. If the sources list
  what is supported and the draft concludes something else is unsupported,
  that is an inference, not a quoted fact, and it is unfaithful.
- Generic courtesy ("sorry to hear that"), apologies, and any promise that a
  colleague, agent or team member will follow up are NOT factual claims. They
  never make a draft unfaithful, even when the sources say nothing about
  following up, and even when they name the topic being followed up on.
  Saying "a team member will follow up about X" is deferring, not claiming.
"""

FAITHFULNESS_PROMPT = """You are checking a draft reply written by a customer-support assistant.

Customer message:
{message}

Draft reply:
{draft}

Sources the draft cited (verbatim):
{sources}

Decide whether every factual claim in the draft (numbers, durations, prices,
policies, conditions, statements about what is or is not supported) is
supported by the cited sources.
""" + GROUNDING_RULES + """
Then give a one-sentence note explaining a false verdict.
"""

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
- faithful: is every factual claim in the draft supported by the cited sources?
- correct: true only if the draft conveys the key facts of the reference
  answer and does not contradict it.
""" + GROUNDING_RULES + """
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
