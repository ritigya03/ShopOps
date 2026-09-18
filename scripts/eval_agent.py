import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from datetime import datetime, timezone

import yaml

from app.agent.graph import AGENT_GRAPH
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.auth import CurrentUser


def load_cases(path: Path) -> list[dict]:
    with path.open() as f:
        return yaml.safe_load(f)


def score_tool_selection(case: dict, result: dict) -> bool:
    return set(result["actual_tools"]) == set(case.get("expected_tools", []))


def score_citation(case: dict, result: dict) -> bool | None:
    expected_doc_id = case.get("expected_citation_doc_id")
    if expected_doc_id is None:
        return None
    return expected_doc_id in result["actual_citation_doc_ids"]


def score_abstention(case: dict, result: dict) -> bool:
    return result["actual_abstain"] == case.get("expect_abstain", False)


def _build_eval_state(case: dict) -> AgentState:
    user = CurrentUser(sub="eval", email="eval@shopops.test", role=case["role"])
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": case["message"]},
        ],
        "user": user,
        "pending_tool_calls": [],
        "tool_results": [],
        "evidence": [],
        "abstain": False,
        "loop_count": 0,
        "answer": None,
        "proposal": None,
    }


def run_case(case: dict) -> dict:
    state = _build_eval_state(case)
    result = AGENT_GRAPH.invoke(state)
    return {
        "case_id": case["id"],
        "message": case["message"],
        "actual_tools": [tr["tool_name"] for tr in result["tool_results"]],
        "actual_citation_doc_ids": [e.doc_id for e in result["evidence"]],
        "actual_abstain": result["abstain"],
        "answer": result["answer"],
    }


CASES_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "cases.yaml"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "data" / "eval" / "results"


def _status_label(ok: bool | None) -> str:
    if ok is None:
        return "N/A"
    return "PASS" if ok else "FAIL"


def main() -> None:
    cases = load_cases(CASES_PATH)
    records = []
    tool_pass = 0
    citation_pass = 0
    citation_total = 0
    abstain_pass = 0

    for case in cases:
        result = run_case(case)
        tool_ok = score_tool_selection(case, result)
        citation_ok = score_citation(case, result)
        abstain_ok = score_abstention(case, result)

        tool_pass += int(tool_ok)
        if citation_ok is not None:
            citation_total += 1
            citation_pass += int(citation_ok)
        abstain_pass += int(abstain_ok)

        print(
            f"[{case['id']}] tools={_status_label(tool_ok)} "
            f"citation={_status_label(citation_ok)} abstain={_status_label(abstain_ok)}"
        )

        records.append({
            "case_id": case["id"],
            "message": case["message"],
            "expected_tools": case.get("expected_tools", []),
            "actual_tools": result["actual_tools"],
            "expected_citation_doc_id": case.get("expected_citation_doc_id"),
            "actual_citation_doc_ids": result["actual_citation_doc_ids"],
            "expect_abstain": case.get("expect_abstain", False),
            "actual_abstain": result["actual_abstain"],
            "answer": result["answer"],
            "tool_selection_pass": tool_ok,
            "citation_pass": citation_ok,
            "abstention_pass": abstain_ok,
        })

    total = len(cases)
    tool_accuracy = tool_pass / total if total else 0.0
    citation_accuracy = citation_pass / citation_total if citation_total else None
    abstention_accuracy = abstain_pass / total if total else 0.0

    print("\n--- Summary ---")
    print(f"Tool-selection accuracy: {tool_accuracy:.0%} ({tool_pass}/{total})")
    if citation_accuracy is not None:
        print(
            f"Citation accuracy: {citation_accuracy:.0%} "
            f"({citation_pass}/{citation_total})"
        )
    else:
        print("Citation accuracy: N/A (no cases with expected_citation_doc_id)")
    print(f"Abstention accuracy: {abstention_accuracy:.0%} ({abstain_pass}/{total})")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"eval_{timestamp}.json"
    output_path.write_text(json.dumps({
        "summary": {
            "total_cases": total,
            "tool_selection_accuracy": tool_accuracy,
            "citation_accuracy": citation_accuracy,
            "abstention_accuracy": abstention_accuracy,
        },
        "cases": records,
    }, indent=2, default=str))
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
