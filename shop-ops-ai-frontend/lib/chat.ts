import { apiFetch } from './api'
import type { PolicyEvidence, CompensationProposal } from './types'

export interface ChatDone {
  conversationId: string
  citations: PolicyEvidence[]
  proposal: CompensationProposal | null
  actionId: string | null
}

export interface ChatStreamHandlers {
  onChunk: (text: string) => void
  onDone: (result: ChatDone) => void
  onError: (message: string) => void
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  let event: string | null = null
  let dataLine: string | null = null
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice('event: '.length)
    else if (line.startsWith('data: ')) dataLine = line.slice('data: '.length)
  }
  if (!event || dataLine === null) return null
  return { event, data: JSON.parse(dataLine) }
}

export async function streamChat(
  conversationId: string | null,
  message: string,
  handlers: ChatStreamHandlers
): Promise<void> {
  let response: Response
  try {
    response = await apiFetch('/chat/stream', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId, message }),
    })
  } catch {
    handlers.onError('Could not reach the server. Please try again.')
    return
  }

  if (!response.ok || !response.body) {
    let detail = `Request failed (${response.status}).`
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response wasn't JSON - keep the generic message
    }
    handlers.onError(detail)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let settled = false

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const parsed = parseSseBlock(block)
        if (parsed?.event === 'chunk') {
          handlers.onChunk(parsed.data as string)
        } else if (parsed?.event === 'done') {
          const d = parsed.data as any
          settled = true
          handlers.onDone({
            conversationId: d.conversation_id,
            citations: d.citations,
            proposal: d.proposal,
            actionId: d.action_id,
          })
        } else if (parsed?.event === 'error') {
          const d = parsed.data as any
          settled = true
          handlers.onError(d.detail ?? 'Something went wrong.')
        }
        boundary = buffer.indexOf('\n\n')
      }
    }
  } catch {
    // Connection dropped or a chunk failed to parse mid-stream (e.g. the
    // backend restarted). Without this, the exception would escape as an
    // unhandled rejection: no error shown, spinner stuck forever. Guarded
    // by `settled` so an abrupt close *after* a clean done/error event
    // (some browsers throw on the final read even post-completion) can't
    // clobber an already-delivered result.
    if (!settled) {
      handlers.onError('Connection lost while streaming the response. Please try again.')
    }
  }
}
