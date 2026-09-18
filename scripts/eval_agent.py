"""LLM eval benchmark for the ShopOps agent.

!!! WARNING — THIS SCRIPT IS NOT READ-ONLY !!!

Every case is executed against the REAL LangGraph agent (`AGENT_GRAPH.invoke`)
using the REAL configured database, Gemini API key and Qdrant instance. That
means running this script:

  * WRITES PERMANENT ROWS to `shopops_ops.audit_events`. That table is
    append-only (a trigger forbids UPDATE and DELETE), so eval audit rows can
    NEVER be cleaned up.
  * MAY CREATE A REAL PENDING APPROVAL. Cases where the agent proposes
    compensation (e.g. `compensation_proposal_moderate`) insert a real
    `PROPOSED` row into `shopops_ops.action_requests`, which shows up in the
    live Approvals dashboard exactly like a human-originated proposal.
  * COSTS REAL MONEY (Gemini API calls) and takes minutes to run.

Eval-created rows are tagged `requested_by='eval'`. To find or reject them:

    SELECT * FROM shopops_ops.action_requests WHERE requested_by = 'eval';

Every action_id created during a run is also recorded in the results JSON
(and printed to the console), so a run is traceable straight from its output.

Usage (from the repo root):

    python scripts/eval_agent.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import json
import subprocess
from datetime import datetime, timezone

import yaml

from app.agent.graph import AGENT_GRAPH
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.auth import CurrentUser
from app.config import settings

WARNING_BANNER = """
================================================================================
!! WARNING: THIS EVAL IS NOT READ-ONLY !!

It invokes the real agent against the configured database. Running it:
  - writes PERMANENT rows to shopops_ops.audit_events (append-only, a trigger
    forbids UPDATE/DELETE, so they can never be removed)
  - may create REAL pending approvals in shopops_ops.action_requests that
    appear in the live Approvals dashboard
  - spends real Gemini API credits

Eval-created rows are tagged requested_by='eval'. To review/reject them:
  SELECT * FROM shopops_ops.action_requests WHERE requested_by = 'eval';

Any action_id created by this run is printed below and stored in the results
JSON file.
================================================================================
"""


def load_cases(path: Path) -> list[dict]:
    with path.open() as f:
        return yaml.safe_load(f) or []


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
    proposal = result.get("proposal")
    return {
        "case_id": case["id"],
        "message": case["message"],
        "actual_tools": [tr["tool_name"] for tr in result["tool_results"]],
        "actual_citation_doc_ids": [e.doc_id for e in result["evidence"]],
        "actual_abstain": result["abstain"],
        "answer": result["answer"],
        # Real approval-queue row created by this case, if any. Traceable via
        # SELECT ... FROM shopops_ops.action_requests WHERE requested_by='eval'.
        "action_id": proposal["action_id"] if proposal else None,
    }


CASES_PATH = REPO_ROOT / "data" / "eval" / "cases.yaml"
RESULTS_DIR = REPO_ROOT / "data" / "eval" / "results"


def _status_label(ok: bool | None) -> str:
    if ok is None:
        return "N/A"
    return "PASS" if ok else "FAIL"


def _git_sha() -> str | None:
    """Best-effort current commit SHA; None if git is unavailable or fails."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
    except Exception:  # noqa: BLE001 - provenance is best-effort, never fatal
        return None
    return proc.stdout.strip() or None


def main() -> None:
    print(WARNING_BANNER)

    cases = load_cases(CASES_PATH)
    records = []
    tool_pass = 0
    citation_pass = 0
    citation_total = 0
    abstain_pass = 0
    error_count = 0

    for case in cases:
        try:
            result = run_case(case)
        except Exception as exc:  # noqa: BLE001 - one bad case must not kill the run
            error_count += 1
            print(f"[{case['id']}] ERROR: {exc}")
            expected_doc_id = case.get("expected_citation_doc_id")
            if expected_doc_id is not None:
                # Counts toward the citation denominator as a failure.
                citation_total += 1
            records.append({
                "case_id": case["id"],
                "message": case["message"],
                "status": "error",
                "error": str(exc),
                "expected_tools": case.get("expected_tools", []),
                "actual_tools": [],
                "expected_citation_doc_id": expected_doc_id,
                "actual_citation_doc_ids": [],
                "expect_abstain": case.get("expect_abstain", False),
                "actual_abstain": None,
                "answer": None,
                "action_id": None,
                "tool_selection_pass": False,
                "citation_pass": False if expected_doc_id is not None else None,
                "abstention_pass": False,
            })
            continue

        tool_ok = score_tool_selection(case, result)
        citation_ok = score_citation(case, result)
        abstain_ok = score_abstention(case, result)

        tool_pass += int(tool_ok)
        if citation_ok is not None:
            citation_total += 1
            citation_pass += int(citation_ok)
        abstain_pass += int(abstain_ok)

        line = (
            f"[{case['id']}] tools={_status_label(tool_ok)} "
            f"citation={_status_label(citation_ok)} abstain={_status_label(abstain_ok)}"
        )
        if result["action_id"] is not None:
            line += f" action_id={result['action_id']}"
        print(line)

        records.append({
            "case_id": case["id"],
            "message": case["message"],
            "status": "ok",
            "error": None,
            "expected_tools": case.get("expected_tools", []),
            "actual_tools": result["actual_tools"],
            "expected_citation_doc_id": case.get("expected_citation_doc_id"),
            "actual_citation_doc_ids": result["actual_citation_doc_ids"],
            "expect_abstain": case.get("expect_abstain", False),
            "actual_abstain": result["actual_abstain"],
            "answer": result["answer"],
            "action_id": result["action_id"],
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
    if error_count:
        print(f"Errored cases: {error_count}/{total} (scored as failures)")

    created_action_ids = [r["action_id"] for r in records if r["action_id"]]
    if created_action_ids:
        print(
            "\nThis run created real pending approvals in "
            "shopops_ops.action_requests (requested_by='eval'): "
            + ", ".join(created_action_ids)
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"eval_{timestamp}.json"
    output_path.write_text(json.dumps({
        "summary": {
            "total_cases": total,
            "error_cases": error_count,
            "tool_selection_accuracy": tool_accuracy,
            "citation_accuracy": citation_accuracy,
            "abstention_accuracy": abstention_accuracy,
            "agent_model": settings.agent_model,
            "git_sha": _git_sha(),
        },
        "cases": records,
    }, indent=2, default=str))
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    main()
