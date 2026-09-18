from pathlib import Path

import yaml


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
