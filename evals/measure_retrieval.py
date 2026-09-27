"""Measure how far apart retrieval distances are for questions the corpus can
answer vs. questions it cannot.

The point: today, an unanswerable question is caught only because the *model*
declines to cite anything. That is model-dependent, which is exactly what the
escalation rules are supposed not to be. A distance threshold would be a
deterministic backstop - but only if answerable and unanswerable questions
actually separate. This script checks whether they do, before any threshold
is chosen.

Embeddings only, no generation, so it is fast and does not touch the
generation rate limit.

    python -m evals.measure_retrieval
"""
import asyncio

from app.services.retrieval import retrieve_chunks
from evals.dataset import load_dataset
from evals.run import ensure_eval_tenant, load_corpus

TOP_K = 5


def _bucket(row: dict) -> str:
    """Rows the corpus genuinely cannot answer vs. rows it can."""
    if "unanswerable" in row["tags"]:
        return "unanswerable"
    if "injection" in row["tags"]:
        return "injection"
    if row["must_cite"]:
        return "answerable"
    # Refunds, complaints, legal: escalated for policy reasons, and the corpus
    # may or may not have something relevant. Not informative either way.
    return "policy-escalated"


async def main() -> None:
    tenant_id = await ensure_eval_tenant()
    await load_corpus(tenant_id)
    rows = load_dataset()

    sem = asyncio.Semaphore(4)

    async def measure(row: dict) -> dict:
        async with sem:
            chunks = await retrieve_chunks(tenant_id, row["message"], k=TOP_K)
        best = chunks[0] if chunks else None
        wanted = [c for c in chunks if c.source_id in row["must_cite"]]
        return {
            "id": row["id"],
            "bucket": _bucket(row),
            "message": row["message"],
            "best_distance": best.distance if best else None,
            "best_source": best.source_id if best else None,
            "wanted_distance": wanted[0].distance if wanted else None,
        }

    results = await asyncio.gather(*(measure(r) for r in rows))

    print(f"{'bucket':<18}{'n':>4}{'min':>8}{'median':>8}{'max':>8}")
    print("-" * 46)
    by_bucket: dict[str, list[float]] = {}
    for r in results:
        if r["best_distance"] is not None:
            by_bucket.setdefault(r["bucket"], []).append(r["best_distance"])
    for bucket in ("answerable", "unanswerable", "injection", "policy-escalated"):
        values = sorted(by_bucket.get(bucket, []))
        if not values:
            continue
        median = values[len(values) // 2]
        print(f"{bucket:<18}{len(values):>4}{values[0]:>8.3f}{median:>8.3f}{values[-1]:>8.3f}")

    answerable = sorted(by_bucket.get("answerable", []))
    unanswerable = sorted(by_bucket.get("unanswerable", []))
    if answerable and unanswerable:
        print(
            f"\nWorst answerable: {answerable[-1]:.3f}   "
            f"Best unanswerable: {unanswerable[0]:.3f}   "
            f"=> {'SEPARATED' if answerable[-1] < unanswerable[0] else 'OVERLAP'}"
        )

    print("\nUnanswerable rows (what the nearest chunk was):")
    for r in sorted(
        (r for r in results if r["bucket"] == "unanswerable"),
        key=lambda r: r["best_distance"] or 0,
    ):
        print(f"  {r['best_distance']:.3f}  {r['id']}  {r['message'][:52]!r} -> {r['best_source']}")

    print("\nAnswerable rows with the most distant correct chunk:")
    with_wanted = [r for r in results if r["wanted_distance"] is not None]
    for r in sorted(with_wanted, key=lambda r: -r["wanted_distance"])[:8]:
        print(f"  {r['wanted_distance']:.3f}  {r['id']}  {r['message'][:52]!r}")

    missing = [r for r in results if r["bucket"] == "answerable" and r["wanted_distance"] is None]
    if missing:
        print("\nAnswerable rows where the wanted chunk was not in top-k at all:")
        for r in missing:
            print(f"  {r['id']}  {r['message'][:60]!r}")


if __name__ == "__main__":
    asyncio.run(main())
