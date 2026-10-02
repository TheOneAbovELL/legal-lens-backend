"""Run the safety questionnaire (normal + negative questions) against the SafetyGuard.

    python scripts/evaluate_safety.py [--questions evaluation/safety_questions.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import PROJECT_ROOT  # noqa: E402
from app.domain.query import SafetyDecision  # noqa: E402
from app.rag.query.normalizer import normalize_query  # noqa: E402
from app.services.safety import SafetyGuard  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--questions", type=Path, default=PROJECT_ROOT / "evaluation" / "safety_questions.json")
    args = p.parse_args()
    questions = json.loads(args.questions.read_text(encoding="utf-8"))["questions"]
    guard = SafetyGuard()
    failures = 0
    for q in questions:
        result = guard.check(normalize_query(q["query"]))
        got = "refuse" if result.decision == SafetyDecision.REFUSE else "allow"
        ok = got == q["expected"]
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  expected={q['expected']:<6} got={got:<6} {result.categories}  {q['query']}")
    total = len(questions)
    print(f"\n{total - failures}/{total} correct ({(total - failures) / total:.0%})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
