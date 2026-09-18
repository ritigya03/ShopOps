import { getSession, logout } from './auth'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const session = getSession()
  const headers = new Headers(options.headers)
  if (session) {
    headers.set('Authorization', `Bearer ${session.idToken}`)
  }
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })

  if (resp.status === 401) {
    logout()
    if (typeof window !== 'undefined') {
      window.location.href = '/login'
    }
  }

  return resp
}
