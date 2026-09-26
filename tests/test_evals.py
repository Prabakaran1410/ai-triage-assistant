from evals.dataset import load_dataset, validate_dataset
from evals.metrics import (
    ESCALATION_RECALL_FLOOR,
    RowResult,
    evaluate_gate,
    find_forbidden_hits,
    summarize,
)


def _row(**overrides) -> RowResult:
    base = {
        "id": "q1", "split": "dev", "message": "m", "tags": [],
        "expected_intent": "general_question", "expected_escalate": False,
        "must_cite": [], "forbidden": [], "predicted_intent": "general_question",
        "escalated": False, "escalation_reason": None, "cited": [], "confidence": 0.9,
        "draft": "ok", "llm_unavailable": False, "latency_s": 1.0,
    }
    base.update(overrides)
    return RowResult(**base)


# --- dataset -----------------------------------------------------------------

def test_shipped_dataset_is_valid():
    assert validate_dataset(load_dataset()) == []


def test_dataset_has_both_splits_and_enough_rows():
    rows = load_dataset()
    assert len(rows) >= 55
    splits = {r["split"] for r in rows}
    assert splits == {"dev", "holdout"}
    holdout = sum(r["split"] == "holdout" for r in rows)
    assert holdout >= 0.2 * len(rows)


def test_dataset_covers_the_hard_cases():
    tags = {t for r in load_dataset() for t in r["tags"]}
    assert {"answerable", "refund", "complaint", "legal", "unanswerable", "stale", "injection"} <= tags


def test_validator_catches_bad_rows():
    bad = [
        {"id": "a", "split": "dev", "message": "x", "intent": "nonsense", "escalate": False,
         "must_cite": ["no-such-source"], "reference": "", "forbidden": [], "tags": []},
        {"id": "a", "split": "test", "message": " ", "intent": None, "escalate": "yes",
         "must_cite": [], "reference": "", "forbidden": [], "tags": []},
    ]
    errors = " | ".join(validate_dataset(bad))
    for expected in ("duplicate id", "unknown intent", "unknown sources", "split must be", "escalate must be", "empty message"):
        assert expected in errors


# --- metrics -----------------------------------------------------------------

def test_forbidden_phrase_match_is_case_insensitive():
    assert find_forbidden_hits("Refunds Are ALWAYS approved", ["refunds are always"]) == ["refunds are always"]
    assert find_forbidden_hits(None, ["x"]) == []


def test_unavailable_rows_are_excluded_from_quality_metrics():
    # The fallback escalates by design; counting it would fake a perfect recall.
    results = [
        _row(id="ok", expected_escalate=True, escalated=True),
        _row(id="down", expected_escalate=True, escalated=True, llm_unavailable=True),
        _row(id="miss", expected_escalate=True, escalated=False),
    ]
    s = summarize(results)
    assert s["scored_rows"] == 2 and s["llm_unavailable_rows"] == 1
    assert s["escalation_recall"] == 0.5 and s["missed_escalations"] == ["miss"]


def test_escalation_and_false_escalation_rates():
    results = [
        _row(id="a", expected_escalate=False, escalated=False),
        _row(id="b", expected_escalate=False, escalated=True),
        _row(id="c", expected_escalate=True, escalated=True),
    ]
    s = summarize(results)
    assert s["false_escalation_rate"] == 0.5
    assert s["escalation_recall"] == 1.0 and s["escalation_precision"] == 0.5
    assert s["false_escalations"] == ["b"]


def test_citation_hit_rate_only_counts_answerable_rows():
    results = [
        _row(id="hit", must_cite=["a"], cited=["a", "z"]),
        _row(id="miss", must_cite=["a"], cited=["z"]),
        _row(id="unanswerable", must_cite=[], expected_escalate=True, escalated=True),
    ]
    s = summarize(results)
    assert s["citation_hit_rate"] == 0.5 and s["citation_misses"] == ["miss"]


def test_intent_accuracy_skips_rows_without_an_expected_intent():
    results = [
        _row(id="right", expected_intent="billing", predicted_intent="billing"),
        _row(id="wrong", expected_intent="billing", predicted_intent="refund"),
        _row(id="adversarial", expected_intent=None, predicted_intent="refund"),
    ]
    s = summarize(results)
    assert s["intent_accuracy"] == 0.5 and s["intent_rows"] == 2


# --- gate ---------------------------------------------------------------------

def _good_summary(**overrides):
    base = {
        "llm_unavailable_rate": 0.0, "escalation_recall": 1.0, "forbidden_violations": 0,
        "missed_escalations": [], "forbidden_violation_ids": [], "intent_accuracy": 0.9,
        "citation_hit_rate": 0.9, "faithfulness": 0.9, "correctness": 0.9, "false_escalation_rate": 0.1,
    }
    base.update(overrides)
    return base


def test_gate_passes_when_nothing_regressed():
    assert evaluate_gate(_good_summary(), _good_summary())[0] == "pass"


def test_gate_fails_below_the_escalation_recall_floor_even_without_a_baseline():
    verdict, reasons = evaluate_gate(
        _good_summary(escalation_recall=ESCALATION_RECALL_FLOOR - 0.1, missed_escalations=["q9"]), None
    )
    assert verdict == "regression" and "q9" in reasons[0]


def test_gate_fails_on_any_forbidden_phrase():
    verdict, _ = evaluate_gate(_good_summary(forbidden_violations=1, forbidden_violation_ids=["q56"]), None)
    assert verdict == "regression"


def test_gate_fails_on_a_drop_beyond_tolerance_but_not_within_it():
    base = _good_summary()
    assert evaluate_gate(_good_summary(intent_accuracy=0.87), base)[0] == "pass"
    assert evaluate_gate(_good_summary(intent_accuracy=0.80), base)[0] == "regression"
    assert evaluate_gate(_good_summary(false_escalation_rate=0.30), base)[0] == "regression"


def test_gate_is_inconclusive_when_the_llm_was_unavailable_too_often():
    verdict, _ = evaluate_gate(_good_summary(llm_unavailable_rate=0.4), _good_summary())
    assert verdict == "inconclusive"
