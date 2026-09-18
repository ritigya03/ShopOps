# Frontend chat wiring — design

Status: approved by user
Date: 2026-09-18
Scope: second of 4 frontend sub-projects (after Auth). Depends on Auth (`lib/auth.ts`, `lib/api.ts`) and the just-added `POST /chat/stream`.

## Decisions carried in from earlier

- Single active conversation for now (no conversation-list sidebar/switcher — no backend endpoint for that yet).
- Real SSE streaming via `/chat/stream`.
- Decorative mock content with no real backing data (order-summary card, risk card, timeline, tool-tags, right-hand context panel, the fixed "refusal" block) is removed — each assistant message renders only what `ChatResponse`/the stream's `done` event actually returns: `answer`, `citations`, `proposal`.

## New file

- **`lib/chat.ts`**: `streamChat(conversationId, message, handlers)` — since browser `EventSource` only supports GET (no custom headers, no POST body), this does a manual `fetch` via `apiFetch('/chat/stream', {method: 'POST', body: ...})`, reads `response.body.getReader()`, decodes and incrementally parses the `event: ...\ndata: ...\n\n` SSE format, and calls `handlers.onChunk(text)` per chunk, `handlers.onDone({conversationId, citations, proposal, actionId})` once, or `handlers.onError(message)` on an `error` event or a thrown exception.

## `ChatPage` rewrite

State: `messages: ChatMessage[]` (`{role, content, citations?, proposal?, actionId?}`), `conversationId: string | null`, `sending: boolean`.

- Composer input is controlled; Enter/Send calls `sendMessage(text)`: appends the user message, appends an empty streaming assistant placeholder, calls `streamChat` — `onChunk` appends to that placeholder's content (live-updating), `onDone` fills in `citations`/`proposal`/`actionId` and stores the returned `conversationId` for the next turn, `onError` replaces the placeholder with an inline error message.
- **Citation** component becomes data-driven: renders one collapsible chip per citation (`doc_id` + `version` + `section`, excerpt in the popover), not the single hardcoded one.
- **Proposal** component becomes read-only: order id, amount, policy doc+version, severity, reason, with a fixed "Submitted · awaiting manager approval" status — no submit button, since the proposal is already created server-side by the time the message renders it.
- "New chat" button resets `messages`/`conversationId` to start a fresh conversation.
- Removed: `RiskCard`, `ToolTags`, the order-summary/`Timeline` block, the fixed `refusal` div, the right-hand context panel, and the fake multi-conversation sidebar list.

## Testing

No test infra in the frontend. Manual: `pnpm dev`, log in, ask an order-status question and a compensation-eligible question, confirm the answer streams in, citations/proposal render correctly when present, "New chat" resets state, and a second message in the same conversation carries context (matches the backend's multi-turn persistence, already verified server-side).
