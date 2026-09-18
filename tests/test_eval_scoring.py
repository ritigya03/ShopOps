import json

from app.agent.prompts import SYSTEM_PROMPT
from scripts import eval_agent
from scripts.eval_agent import (
    _build_eval_state,
    load_cases,
    main,
    score_abstention,
    score_citation,
    score_tool_selection,
)


def test_load_cases_parses_yaml(tmp_path):
    cases_file = tmp_path / "cases.yaml"
    cases_file.write_text("""
- id: sample_case
  message: "hello"
  role: Viewer
  expected_tools: [get_order]
""")
    cases = load_cases(cases_file)
    assert cases == [{"id": "sample_case", "message": "hello", "role": "Viewer", "expected_tools": ["get_order"]}]


def test_score_tool_selection_matches_exact_set():
    case = {"expected_tools": ["get_order", "estimate_delivery_risk"]}
    result = {"actual_tools": ["estimate_delivery_risk", "get_order"]}
    assert score_tool_selection(case, result) is True


def test_score_tool_selection_detects_mismatch():
    case = {"expected_tools": ["get_order"]}
    result = {"actual_tools": ["get_seller_metrics"]}
    assert score_tool_selection(case, result) is False


def test_score_tool_selection_defaults_to_empty_expected():
    case = {}
    result = {"actual_tools": []}
    assert score_tool_selection(case, result) is True


def test_score_citation_returns_none_when_not_applicable():
    case = {}
    result = {"actual_citation_doc_ids": ["POL-COMP-001"]}
    assert score_citation(case, result) is None


def test_score_citation_matches_expected_doc_id():
    case = {"expected_citation_doc_id": "POL-COMP-001"}
    result = {"actual_citation_doc_ids": ["POL-DELIVERY-001", "POL-COMP-001"]}
    assert score_citation(case, result) is True


def test_score_citation_detects_missing_doc_id():
    case = {"expected_citation_doc_id": "POL-COMP-001"}
    result = {"actual_citation_doc_ids": ["POL-DELIVERY-001"]}
    assert score_citation(case, result) is False


def test_score_abstention_matches_expected_true():
    case = {"expect_abstain": True}
    result = {"actual_abstain": True}
    assert score_abstention(case, result) is True


def test_score_abstention_defaults_to_expected_false():
    case = {}
    result = {"actual_abstain": False}
    assert score_abstention(case, result) is True


def test_score_abstention_detects_mismatch():
    case = {"expect_abstain": True}
    result = {"actual_abstain": False}
    assert score_abstention(case, result) is False


def test_build_eval_state_shapes_initial_agent_state():
    case = {"message": "What is the status of order abc123?", "role": "SupportAgent"}
    state = _build_eval_state(case)

    assert state["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "What is the status of order abc123?"},
    ]
    assert state["user"].sub == "eval"
    assert state["user"].role == "SupportAgent"
    assert state["pending_tool_calls"] == []
    assert state["tool_results"] == []
    assert state["evidence"] == []
    assert state["abstain"] is False
    assert state["loop_count"] == 0
    assert state["answer"] is None
    assert state["proposal"] is None


def test_load_cases_returns_empty_list_for_empty_file(tmp_path):
    cases_file = tmp_path / "cases.yaml"
    cases_file.write_text("# only a comment, no cases\n")
    assert load_cases(cases_file) == []


# --- main() wiring / aggregation -------------------------------------------
#
# Three cases, fully mocked (no Gemini/Postgres/Qdrant). Canned results are
# keyed by case id, so pairing case[i] with result[j != i] changes the scores
# and the per-case actuals, and the assertions below catch it.
#
# tool selection:  alpha PASS, beta PASS, gamma FAIL  -> 2/3
# citation:        alpha N/A,  beta PASS, gamma FAIL  -> 1/2
# abstention:      alpha PASS, beta PASS, gamma FAIL  -> 2/3

FIXTURE_CASES_YAML = """
- id: c_alpha
  message: "alpha message"
  role: Viewer
  expected_tools: [get_order]

- id: c_beta
  message: "beta message"
  role: Viewer
  expected_tools: [search_policy]
  expected_citation_doc_id: POL-BETA-001

- id: c_gamma
  message: "gamma message"
  role: Viewer
  expected_tools: [search_policy]
  expected_citation_doc_id: POL-GAMMA-001
"""

FAKE_RESULTS = {
    "c_alpha": {
        "actual_tools": ["get_order"],
        "actual_citation_doc_ids": [],
        "actual_abstain": False,
        "answer": "alpha answer",
        "action_id": None,
    },
    "c_beta": {
        "actual_tools": ["search_policy"],
        "actual_citation_doc_ids": ["POL-BETA-001"],
        "actual_abstain": False,
        "answer": "beta answer",
        "action_id": "action-beta-42",
    },
    "c_gamma": {
        "actual_tools": ["get_order"],
        "actual_citation_doc_ids": ["POL-OTHER-001"],
        "actual_abstain": True,
        "answer": "gamma answer",
        "action_id": None,
    },
}


def _write_results_json(tmp_path, monkeypatch, run_case_impl):
    cases_file = tmp_path / "cases.yaml"
    cases_file.write_text(FIXTURE_CASES_YAML)
    results_dir = tmp_path / "results"

    monkeypatch.setattr(eval_agent, "CASES_PATH", cases_file)
    monkeypatch.setattr(eval_agent, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(eval_agent, "run_case", run_case_impl)

    main()

    written = list(results_dir.glob("eval_*.json"))
    assert len(written) == 1
    return json.loads(written[0].read_text())


def test_main_aggregates_and_pairs_each_case_with_its_own_result(
    tmp_path, monkeypatch, capsys
):
    def fake_run_case(case):
        return {"case_id": case["id"], "message": case["message"], **FAKE_RESULTS[case["id"]]}

    payload = _write_results_json(tmp_path, monkeypatch, fake_run_case)

    summary = payload["summary"]
    assert summary["total_cases"] == 3
    assert summary["error_cases"] == 0
    assert summary["tool_selection_accuracy"] == 2 / 3
    assert summary["citation_accuracy"] == 0.5
    assert summary["abstention_accuracy"] == 2 / 3
    assert summary["agent_model"] == eval_agent.settings.agent_model
    assert "git_sha" in summary

    records = payload["cases"]
    assert [r["case_id"] for r in records] == ["c_alpha", "c_beta", "c_gamma"]
    for record in records:
        canned = FAKE_RESULTS[record["case_id"]]
        assert record["actual_tools"] == canned["actual_tools"]
        assert record["actual_citation_doc_ids"] == canned["actual_citation_doc_ids"]
        assert record["actual_abstain"] == canned["actual_abstain"]
        assert record["action_id"] == canned["action_id"]
        assert record["status"] == "ok"

    assert [r["tool_selection_pass"] for r in records] == [True, True, False]
    assert [r["citation_pass"] for r in records] == [None, True, False]
    assert [r["abstention_pass"] for r in records] == [True, True, False]

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "requested_by='eval'" in out
    assert "action_id=action-beta-42" in out
    assert "[c_alpha] tools=PASS citation=N/A abstain=PASS" in out
    assert "action_id" not in out.split("[c_alpha]")[1].split("\n")[0]


def test_main_isolates_a_failing_case_and_still_writes_results(
    tmp_path, monkeypatch, capsys
):
    def fake_run_case(case):
        if case["id"] == "c_beta":
            raise RuntimeError("rate limited")
        return {"case_id": case["id"], "message": case["message"], **FAKE_RESULTS[case["id"]]}

    payload = _write_results_json(tmp_path, monkeypatch, fake_run_case)

    summary = payload["summary"]
    assert summary["total_cases"] == 3
    assert summary["error_cases"] == 1
    # c_alpha passes tools, c_gamma fails, c_beta errors -> 1/3
    assert summary["tool_selection_accuracy"] == 1 / 3
    # c_beta and c_gamma both have expected_citation_doc_id, neither passes
    assert summary["citation_accuracy"] == 0.0
    assert summary["abstention_accuracy"] == 1 / 3

    records = payload["cases"]
    assert [r["case_id"] for r in records] == ["c_alpha", "c_beta", "c_gamma"]
    errored = records[1]
    assert errored["status"] == "error"
    assert errored["error"] == "rate limited"
    assert errored["tool_selection_pass"] is False
    assert errored["citation_pass"] is False
    assert errored["abstention_pass"] is False
    assert errored["action_id"] is None

    out = capsys.readouterr().out
    assert "[c_beta] ERROR: rate limited" in out


def test_main_writes_results_even_when_every_case_errors(tmp_path, monkeypatch):
    def fake_run_case(case):
        raise RuntimeError("everything is down")

    payload = _write_results_json(tmp_path, monkeypatch, fake_run_case)

    assert payload["summary"]["error_cases"] == 3
    assert payload["summary"]["tool_selection_accuracy"] == 0.0
    assert payload["summary"]["citation_accuracy"] == 0.0
    assert payload["summary"]["abstention_accuracy"] == 0.0
    assert all(r["status"] == "error" for r in payload["cases"])
