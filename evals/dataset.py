"""Load and validate the labeled dataset. No network access, so it can run in
unit tests: a malformed dataset should fail CI immediately, not halfway
through a paid evaluation run."""
import json
import pathlib
from collections import Counter
from typing import Any

from app.models.triage import Intent
from evals.corpus import CORPUS

DATASET_PATH = pathlib.Path(__file__).parent / "dataset.jsonl"
VALID_SPLITS = {"dev", "holdout"}
VALID_INTENTS = {i.value for i in Intent}
REQUIRED_KEYS = {"id", "split", "message", "intent", "escalate", "must_cite", "reference", "forbidden", "tags"}


def load_dataset(path: pathlib.Path = DATASET_PATH) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path.name} line {line_number}: invalid JSON ({e})") from e
    return rows


def validate_dataset(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    corpus_ids = {c.source_id for c in CORPUS}

    ids = Counter(r.get("id") for r in rows)
    errors += [f"duplicate id {i!r}" for i, n in ids.items() if n > 1]

    for r in rows:
        rid = r.get("id", "<missing id>")
        missing = REQUIRED_KEYS - r.keys()
        if missing:
            errors.append(f"{rid}: missing keys {sorted(missing)}")
            continue
        if r["split"] not in VALID_SPLITS:
            errors.append(f"{rid}: split must be one of {sorted(VALID_SPLITS)}")
        if r["intent"] is not None and r["intent"] not in VALID_INTENTS:
            errors.append(f"{rid}: unknown intent {r['intent']!r}")
        if not isinstance(r["escalate"], bool):
            errors.append(f"{rid}: escalate must be true/false")
        if not r["message"].strip():
            errors.append(f"{rid}: empty message")
        unknown = [s for s in r["must_cite"] if s not in corpus_ids]
        if unknown:
            errors.append(f"{rid}: must_cite references unknown sources {unknown}")
        if r["must_cite"] and not r["escalate"] and not r["reference"].strip():
            errors.append(f"{rid}: an answerable row needs a reference answer")
    return errors
