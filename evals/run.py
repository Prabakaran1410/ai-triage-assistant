"""Run the labeled dataset through the real triage pipeline and score it.

    python -m evals.run                      # score, compare to baseline
    python -m evals.run --split dev          # dev rows only
    python -m evals.run --force-baseline     # record this run as the baseline

Exit code: 0 pass, 1 regression, 2 inconclusive (the LLM was unavailable for
too many rows to say anything about quality).

This calls the same `run_triage` the API endpoint uses, in-process, against a
dedicated evaluation tenant whose knowledge base is the sample corpus in
evals/corpus.py. It needs a database (APP_DATABASE_URL) and GOOGLE_API_KEY.

Discipline that keeps the numbers honest: tune prompts and rules against the
`dev` split only. The `holdout` split is reported separately and must not be
used to decide what to change; look at it to check the tuning generalised.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import os
import pathlib
import sys
import time
import uuid
from typing import Any

from sqlalchemy import text

from app.api.triage import LLM_UNAVAILABLE, run_triage
from app.core import tracing
from app.core.db import get_engine
from app.models.triage import TriageRequest
from app.services.ingest import KnowledgeChunk, replace_tenant_knowledge
from evals.corpus import CORPUS
from evals.dataset import load_dataset, validate_dataset
from evals.judge import judge
from evals.metrics import RowResult, evaluate_gate, find_forbidden_hits, summarize_by_split

EVAL_DIR = pathlib.Path(__file__).parent
BASELINE_PATH = EVAL_DIR / "baseline.json"
REPORTS_DIR = EVAL_DIR / "reports"
TENANT_NAME = "Evaluation - Northwind Outfitters (sample data)"
RETRY_PAUSE_S = 20


async def ensure_eval_tenant() -> str:
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("select id from tenants where name = :name order by created_at limit 1"),
                {"name": TENANT_NAME},
            )
        ).fetchone()
        if row is not None:
            return str(row.id)
        tenant_id = str(uuid.uuid4())
        await conn.execute(
            text("insert into tenants (id, name) values (:id, :name)"),
            {"id": tenant_id, "name": TENANT_NAME},
        )
        return tenant_id


async def load_corpus(tenant_id: str) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    chunks = [
        KnowledgeChunk(c.source_id, c.title, c.content, now - dt.timedelta(days=c.age_days))
        for c in CORPUS
    ]
    return await replace_tenant_knowledge(tenant_id, chunks)


async def run_row(sem: asyncio.Semaphore, row: dict[str, Any], tenant_id: str) -> RowResult:
    async with sem:
        started = time.perf_counter()
        try:
            response, _model = await run_triage(TriageRequest(message=row["message"]), tenant_id)
            intent = response.intent.value
            unavailable = response.escalation_reason == LLM_UNAVAILABLE
            escalated, reason = response.escalate, response.escalation_reason
            cited = [c.source_id for c in response.citations]
            confidence, draft = response.confidence, response.draft_reply
        except Exception as e:  # noqa: BLE001 - retrieval/embedding outage etc; not a quality signal, must not abort the run
            intent, unavailable, escalated = "other", True, True
            reason, cited, confidence, draft = f"pipeline error: {type(e).__name__}: {e}"[:200], [], 0.0, None
        latency = time.perf_counter() - started

    return RowResult(
        id=row["id"],
        split=row["split"],
        message=row["message"],
        tags=row["tags"],
        expected_intent=row["intent"],
        expected_escalate=row["escalate"],
        must_cite=row["must_cite"],
        forbidden=row["forbidden"],
        predicted_intent=intent,
        escalated=escalated,
        escalation_reason=reason,
        cited=cited,
        confidence=confidence,
        draft=draft,
        llm_unavailable=unavailable,
        latency_s=latency,
        forbidden_hits=find_forbidden_hits(draft, row["forbidden"]),
    )


async def judge_row(sem: asyncio.Semaphore, result: RowResult, row: dict[str, Any]) -> None:
    if result.llm_unavailable or not result.draft or not row["reference"].strip():
        return
    by_id = {c.source_id: c.content for c in CORPUS}
    sources = [by_id[s] for s in result.cited if s in by_id]
    async with sem:
        try:
            verdict = await judge(result.message, result.draft, sources, row["reference"])
        except Exception as e:  # noqa: BLE001 - one failed judge call must not abort the run
            result.judge_note = f"judge failed: {type(e).__name__}"
            return
    result.faithful, result.correct, result.judge_note = verdict.faithful, verdict.correct, verdict.note


def pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}%"


def secs(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}s"


def print_report(summary: dict[str, dict[str, Any]], results: list[RowResult], verdict: str, reasons: list[str], baseline: dict[str, Any] | None) -> None:
    splits = [s for s in ("all", "dev", "holdout") if s in summary]
    print()
    print(f"{'metric':<26}" + "".join(f"{s:>10}" for s in splits) + ("   baseline" if baseline else ""))
    print("-" * (26 + 10 * len(splits) + (11 if baseline else 0)))
    rows = [
        ("rows scored / total", None),
        ("intent accuracy", "intent_accuracy"),
        ("escalation recall", "escalation_recall"),
        ("escalation precision", "escalation_precision"),
        ("false escalation rate", "false_escalation_rate"),
        ("citation hit rate", "citation_hit_rate"),
        ("faithfulness (judge)", "faithfulness"),
        ("correctness (judge)", "correctness"),
        ("LLM unavailable rate", "llm_unavailable_rate"),
    ]
    for label, key in rows:
        if key is None:
            cells = "".join(f"{summary[s]['scored_rows']:>4}/{summary[s]['rows']:<5}" for s in splits)
            print(f"{label:<26}{cells}")
            continue
        cells = "".join(f"{pct(summary[s][key]):>10}" for s in splits)
        base = f"{pct(baseline.get(key)):>11}" if baseline else ""
        print(f"{label:<26}{cells}{base}")
    allsum = summary["all"]
    print(f"{'forbidden-phrase hits':<26}{allsum['forbidden_violations']:>10}")
    print(f"{'latency p50 / p95':<26}{secs(allsum['latency_p50_s']):>10}{secs(allsum['latency_p95_s']):>10}")

    print("\nIntent confusion (rows = expected, columns = predicted):")
    for expected, preds in sorted(allsum["confusion"].items()):
        cells = ", ".join(f"{p}:{n}" for p, n in sorted(preds.items(), key=lambda kv: -kv[1]))
        print(f"  {expected:<17} {cells}")

    by_id = {r.id: r for r in results}

    def show(title: str, ids: list[str], describe) -> None:
        # Holdout rows are counted but never itemised: looking at the specific
        # messages the system fails on is exactly how a holdout stops being one.
        if not ids:
            return
        dev_ids = [i for i in ids if by_id[i].split != "holdout"]
        held_back = len(ids) - len(dev_ids)
        print(f"\n{title}:")
        for i in dev_ids:
            r = by_id[i]
            print(f"  {r.id} [{r.split}] {r.message[:70]!r}\n        {describe(r)}")
        if held_back:
            print(f"  (+{held_back} holdout row(s), not itemised)")

    show("MISSED ESCALATIONS (should have gone to a human)", allsum["missed_escalations"],
         lambda r: f"intent={r.predicted_intent} conf={r.confidence:.2f} cited={r.cited} draft={str(r.draft)[:90]!r}")
    show("FALSE ESCALATIONS (could have been answered)", allsum["false_escalations"],
         lambda r: f"reason={r.escalation_reason} intent={r.predicted_intent} conf={r.confidence:.2f} cited={r.cited}")
    show("CITATION MISSES", allsum["citation_misses"],
         lambda r: f"wanted={r.must_cite} got={r.cited}")
    show("FORBIDDEN PHRASES IN REPLY", allsum["forbidden_violation_ids"],
         lambda r: f"hits={r.forbidden_hits} draft={str(r.draft)[:120]!r}")
    wrong_intent = [r.id for r in results if not r.llm_unavailable and r.expected_intent is not None and r.predicted_intent != r.expected_intent]
    show("WRONG INTENT", wrong_intent, lambda r: f"expected={r.expected_intent} got={r.predicted_intent}")
    judged_bad = [r.id for r in results if r.faithful is False or r.correct is False]
    show("JUDGE FLAGGED", judged_bad, lambda r: f"faithful={r.faithful} correct={r.correct} note={r.judge_note}")
    show("LLM UNAVAILABLE", [r.id for r in results if r.llm_unavailable], lambda r: f"{r.escalation_reason}")

    print(f"\nVERDICT: {verdict.upper()}")
    for reason in reasons:
        print(f"  - {reason}")


async def main_async(args: argparse.Namespace) -> int:
    if not args.trace:
        tracing.disable_tracer()
    # Provider outages/rate limits are expected during a run: they are counted
    # and reported per row (and retried once), so the API's full-traceback
    # logging for them is just noise here.
    logging.getLogger("app.api.triage").setLevel(logging.CRITICAL)

    rows = load_dataset()
    problems = validate_dataset(rows)
    if problems:
        print("Dataset is invalid:", *problems, sep="\n  - ")
        return 3
    if args.split != "all":
        rows = [r for r in rows if r["split"] == args.split]
    if args.limit:
        rows = rows[: args.limit]

    tenant_id = await ensure_eval_tenant()
    loaded = await load_corpus(tenant_id)
    print(f"Evaluation tenant {tenant_id}: loaded {loaded} knowledge chunks; running {len(rows)} messages "
          f"(concurrency {args.concurrency}).")

    sem = asyncio.Semaphore(args.concurrency)
    results = list(await asyncio.gather(*(run_row(sem, row, tenant_id) for row in rows)))
    rows_by_id = {r["id"]: r for r in rows}

    # A provider hiccup should not read as a quality drop: retry those rows once.
    retry = [r for r in results if r.llm_unavailable]
    if retry:
        print(f"{len(retry)} row(s) hit an unavailable LLM; retrying once after {RETRY_PAUSE_S}s...")
        await asyncio.sleep(RETRY_PAUSE_S)
        again = await asyncio.gather(*(run_row(sem, rows_by_id[r.id], tenant_id) for r in retry))
        replacements = {r.id: r for r in again}
        results = [replacements.get(r.id, r) for r in results]

    if not args.no_judge:
        await asyncio.gather(*(judge_row(sem, r, rows_by_id[r.id]) for r in results))

    summary = summarize_by_split(results)
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["summary"] if BASELINE_PATH.exists() else None
    verdict, reasons = evaluate_gate(summary["all"], baseline)
    print_report(summary, results, verdict, reasons, baseline)

    REPORTS_DIR.mkdir(exist_ok=True)
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_sha": os.environ.get("GITHUB_SHA"),
        "split": args.split,
        "verdict": verdict,
        "reasons": reasons,
        "summary": summary,
        "rows": [r.to_dict() for r in results],
    }
    out = pathlib.Path(args.output) if args.output else REPORTS_DIR / "latest.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report: {out}")

    if args.force_baseline:
        if verdict == "inconclusive":
            print("Refusing to record an inconclusive run as the baseline.")
        elif args.split != "all":
            print("Refusing to record a partial-split run as the baseline.")
        else:
            BASELINE_PATH.write_text(
                json.dumps({"recorded_at": report["generated_at"], "git_sha": report["git_sha"], "summary": summary["all"]}, indent=2),
                encoding="utf-8",
            )
            print(f"Baseline written to {BASELINE_PATH}")

    return {"pass": 0, "regression": 1, "inconclusive": 2}[verdict]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=["all", "dev", "holdout"], default="all")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="only the first N rows (debugging)")
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM judge (faster, no faithfulness/correctness)")
    parser.add_argument("--trace", action="store_true", help="send a Langfuse trace per row (off by default)")
    parser.add_argument("--output", help="where to write the JSON report")
    parser.add_argument("--force-baseline", action="store_true", help="record this run as evals/baseline.json")
    sys.exit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
