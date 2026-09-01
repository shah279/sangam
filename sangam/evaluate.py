"""Fixture-based extraction evaluation, deterministic by default.

Run snapshots without API cost:
    python3 -m sangam.evaluate

Re-run the same cases through the configured Gemini model:
    python3 -m sangam.evaluate --live
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config, extract, normalize


DEFAULT_FIXTURE = config.ROOT / "tests" / "fixtures" / "extraction_eval.json"


def _identity(row: dict) -> tuple[str, str]:
    name = row.get("resolved_symbol") or f"RAW:{normalize.key(row.get('raw_mention') or '')}"
    return name, row.get("instrument_type") or ""


def evaluate(path: Path = DEFAULT_FIXTURE, *, live: bool = False) -> dict:
    cases = json.loads(path.read_text(encoding="utf-8"))
    true_positive = false_positive = false_negative = action_correct = 0
    resolved = actual_total = 0
    failures: list[str] = []

    for case in cases:
        if live:
            prompt = f"TITLE: {case['title']}\n\nTRANSCRIPT:\n{case['text']}"
            model_output = extract._generate(prompt)
        else:
            model_output = case["model_output"]
        cap = (
            config.DESC_ONLY_MAX_CONFIDENCE
            if case.get("source") == "description"
            else 1.0
        )
        rows = extract._rows_from_result(model_output, cap)
        actual = {_identity(row): row for row in rows}
        expected = {
            (item["symbol"], item["instrument_type"]): item
            for item in case.get("expected", [])
        }
        actual_keys, expected_keys = set(actual), set(expected)
        matched = actual_keys & expected_keys
        true_positive += len(matched)
        false_positive += len(actual_keys - expected_keys)
        false_negative += len(expected_keys - actual_keys)
        action_correct += sum(
            actual[key].get("action") == expected[key].get("action") for key in matched
        )
        actual_total += len(rows)
        resolved += sum(bool(row.get("resolved_symbol")) for row in rows)

        for key in matched:
            maximum = expected[key].get("max_confidence")
            if maximum is not None and actual[key]["confidence"] > maximum:
                failures.append(
                    f"{case['name']}: confidence {actual[key]['confidence']} exceeds {maximum}"
                )
        if actual_keys != expected_keys:
            failures.append(
                f"{case['name']}: missing={sorted(expected_keys - actual_keys)} "
                f"extra={sorted(actual_keys - expected_keys)}"
            )

    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    action_accuracy = action_correct / max(1, true_positive)
    metrics = {
        "cases": len(cases),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "action_accuracy": round(action_accuracy, 4),
        "normalization_coverage": round(resolved / max(1, actual_total), 4),
        "failures": failures,
    }
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--live", action="store_true", help="call Gemini instead of snapshots")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    metrics = evaluate(args.fixture, live=args.live)
    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print(
            "evaluation: "
            f"{metrics['cases']} cases | precision={metrics['precision']:.1%} | "
            f"recall={metrics['recall']:.1%} | actions={metrics['action_accuracy']:.1%} | "
            f"normalized={metrics['normalization_coverage']:.1%}"
        )
        for failure in metrics["failures"]:
            print(f"  ! {failure}")
    if metrics["failures"] or metrics["precision"] < 0.9 or metrics["recall"] < 0.9:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
