# Backend streaming for /chat — design

Status: approved by user
Date: 2026-09-18
Scope: backend only. Unblocks the frontend chat-wiring sub-project (next).

## What this adds

`POST /chat` stays exactly as-is (plain JSON, used by the existing test suite and everything else). New additive endpoint `POST /chat/stream` streams the final answer text via SSE, since that's the only part of a turn worth streaming — tool selection/execution has no user-facing text to stream.

## Design

- **`app/agent/graph.py`**: add `ROUTING_GRAPH` — same `route_or_tools`/`execute_tools`/`validate_evidence` nodes as `AGENT_GRAPH`, wired to stop after `validate_evidence` instead of continuing to `synthesize`/`propose_or_finalize`. No node logic duplicated.
- **`app/agent/llm.py`**: add `stream_model(messages)` — `litellm.completion(..., stream=True)`, yields each non-empty text delta.
- **`app/routes.py`**: add `POST /chat/stream`. Same request/auth/conversation-loading logic as `/chat`, then:
  1. Run `ROUTING_GRAPH.invoke(state)`.
  2. If `state["answer"]` is already set (no tools needed) or `state["abstain"]` is `True` → send that fixed text as one SSE `chunk` event.
  3. Otherwise → call `stream_model(state["messages"])`, forward each delta as an SSE `chunk` event, accumulate into the full answer.
  4. Set `state["answer"]` to the accumulated text, run `propose_or_finalize(state)`, then `append_messages(...)` (same persistence as `/chat`).
  5. Send one final SSE `done` event: `{conversation_id, citations, proposal, action_id}`.
  6. On any exception during steps 1-4: send an SSE `error` event (`{detail}`) and stop — do **not** call `append_messages`, so a failed turn never gets persisted as if it succeeded.

SSE format: `event: <chunk|done|error>\ndata: <json>\n\n`, `media_type="text/event-stream"`.

## Testing

`tests/test_chat_stream_route.py` (integration, real Gemini): use `httpx`'s streaming client against the running app to assert ≥1 `chunk` event arrives, followed by exactly one `done` event shaped like `ChatResponse` minus `answer` (the answer is reconstructed client-side from the chunks). Also: a conversation started via `/chat/stream` is loadable by a follow-up `/chat` call (same persistence table, so history round-trips across the two endpoints).
