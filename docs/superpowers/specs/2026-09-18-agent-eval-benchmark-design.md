# LLM evaluation benchmark — design

## 1. Goal

Add a standalone eval script that benchmarks the LangGraph agent against a curated set of sample queries, scoring tool-selection accuracy, policy-citation correctness, and abstention accuracy (a practical proxy for hallucination rate). This is sub-project 2 of the 3-part observability/eval scope from the TDD (§9/§10) — Langfuse tracing (sub-project 1 of that scope, not yet started) is explicitly deferred; structured JSON logging + CloudWatch (sub-project 3) is already merged (`docs/superpowers/specs/2026-09-18-structured-logging-design.md`).

## 2. Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| Invocation path | Direct `AGENT_GRAPH.invoke()`, not HTTP | No live Cognito tokens needed; focuses purely on agent behavior (tool selection, citations, abstention), which auth/HTTP is already covered for elsewhere ([[project_observability_rollout]] tests) |
| Hallucination detection | Abstention-accuracy proxy, not LLM-as-judge | True hallucination detection needs a judge model checking claims against tool output — bigger scope. Abstention accuracy (correct abstain AND correct non-abstain) is a cheap, deterministic stand-in for this MVP |
| Test case format | YAML file | Matches existing project convention (policy docs use YAML frontmatter, `PyYAML` already a dependency) |
| Where it lives | `scripts/eval_agent.py` + `data/eval/cases.yaml` | Matches existing `scripts/` one-off-script convention (`ingest.py`, `search_policy.py`, etc.) |
| CI integration | None — manually triggered | Makes real Gemini API calls (cost + latency); not something every CI run should pay for, same reasoning as the existing `@pytest.mark.integration` tests being opt-in |

## 3. Test case shape

Each case in `data/eval/cases.yaml` is a YAML mapping:

```yaml
- id: order_status_lookup
  message: "What is the status of order 00010242fe8c5a6d1ba2dd792cb16214?"
  role: Viewer
  expected_tools: [get_order]

- id: delayed_compensation_proposal
  message: "Order 33a3edb84b9df4cb49546859b990ac6d was delivered late, can you propose compensation?"
  role: SupportAgent
  expected_tools: [get_order, estimate_delivery_risk, calculate_compensation]
  expected_citation_doc_id: POL-COMP-001

- id: out_of_scope_refusal
  message: "What's the weather like today?"
  role: Viewer
  expected_tools: []
  expect_abstain: true
```

Fields:
- `id` (required) — unique slug, used in reports.
- `message` (required) — the single user turn sent to the agent.
- `role` (required) — one of `Viewer`, `SupportAgent`, `OperationsManager`. Used to construct a `CurrentUser` directly (no JWT decode).
- `expected_tools` (optional, default `[]`) — tool names expected to appear in `result["tool_results"]`; compared as a set (order-independent).
- `expected_citation_doc_id` (optional) — if present, `result["evidence"]` must contain a `PolicyEvidence` with this `doc_id`.
- `expect_abstain` (optional, default `false`) — if `true`, `result["abstain"]` must be `True`; if `false` (default), it must be `False`. This means every case is scored on abstention accuracy, not just the ones expected to abstain — a case that unexpectedly triggers abstention is exactly the "over-abstention" failure mode this proxy is meant to catch.

Scope: single-turn cases only. Multi-turn conversation behavior is already covered by `tests/test_chat_route.py::test_conversation_persists_across_turns`; this eval only exercises within-turn agent reasoning.

## 4. Architecture

**`scripts/eval_agent.py`:**
- `load_cases(path: Path) -> list[dict]` — reads and parses the YAML file.
- `run_case(case: dict) -> dict` — builds an `AgentState` (system prompt + one user message, a `CurrentUser(sub="eval", email="eval@shopops.test", role=case["role"])`, all other fields at their initial empty values matching `routes.py::_build_chat_state`), calls `AGENT_GRAPH.invoke(state)`, and returns a result record: `{case_id, message, actual_tools, actual_citation_doc_ids, actual_abstain, answer}`.
- `score_tool_selection(case: dict, result: dict) -> bool` — `set(result["actual_tools"]) == set(case.get("expected_tools", []))`. Pure function, no I/O.
- `score_citation(case: dict, result: dict) -> bool | None` — returns `None` (not applicable) if `case` has no `expected_citation_doc_id`; otherwise `case["expected_citation_doc_id"] in result["actual_citation_doc_ids"]`. Pure function.
- `score_abstention(case: dict, result: dict) -> bool` — `result["actual_abstain"] == case.get("expect_abstain", False)`. Pure function.
- `main()` — loads cases, runs each through `run_case`, scores each with the three functions above, prints a per-case report line and an aggregate summary (percentage pass rate per dimension, computed only over applicable cases for citation), writes a timestamped JSON file to `data/eval/results/eval_<UTC-ISO-timestamp>.json` containing per-case results, scores, and the aggregate summary.

## 5. Testing

- `tests/test_eval_scoring.py` — unit tests for `score_tool_selection`, `score_citation`, `score_abstention` against hand-built case/result dicts. No LLM calls, no `@pytest.mark.integration` marker — these are pure functions.
- `run_case` and `main()` are not unit-tested (they require live Gemini/Postgres/Qdrant) — running `scripts/eval_agent.py` manually is itself the verification, same as the existing integration test suite requires live infra to execute.

## 6. Explicitly out of scope (this spec)

- LLM-as-judge hallucination detection (checking whether stated facts are actually grounded in tool output) — flagged as a possible future enhancement if the abstention-accuracy proxy proves insufficient.
- Multi-turn eval cases.
- CI wiring / scheduled runs of the eval script.
- Langfuse tracing (separate, not-yet-started sub-project).
