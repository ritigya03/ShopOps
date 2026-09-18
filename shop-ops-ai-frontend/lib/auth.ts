export type Role = 'Viewer' | 'SupportAgent' | 'OperationsManager'

export interface Session {
  idToken: string
  email: string
  role: Role
  exp: number
}

const STORAGE_KEY = 'shopops_auth'

// Mirrors app/auth.py's _ROLE_PRIORITY on the backend - keep in sync.
const ROLE_PRIORITY: Role[] = ['OperationsManager', 'SupportAgent', 'Viewer']

export class AuthError extends Error {}

function decodeJwtPayload(token: string): Record<string, any> {
  const payload = token.split('.')[1]
  const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  const json = decodeURIComponent(
    atob(padded)
      .split('')
      .map((c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
      .join('')
  )
  return JSON.parse(json)
}

function primaryRole(groups: string[] | undefined): Role | null {
  if (!groups) return null
  for (const role of ROLE_PRIORITY) {
    if (groups.includes(role)) return role
  }
  return null
}

export async function login(email: string, password: string): Promise<Session> {
  const region = process.env.NEXT_PUBLIC_COGNITO_REGION
  const clientId = process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID

  const resp = await fetch(`https://cognito-idp.${region}.amazonaws.com/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
    },
    body: JSON.stringify({
      AuthFlow: 'USER_PASSWORD_AUTH',
      ClientId: clientId,
      AuthParameters: { USERNAME: email, PASSWORD: password },
    }),
  })

  const data = await resp.json()

  if (!resp.ok) {
    throw new AuthError(data.message || 'Sign in failed. Check your email and password.')
  }

  const idToken: string = data.AuthenticationResult.IdToken
  const claims = decodeJwtPayload(idToken)
  const role = primaryRole(claims['cognito:groups'])
  if (!role) {
    throw new AuthError('Your account has no recognized role assigned.')
  }

  const session: Session = {
    idToken,
    email: claims.email ?? email,
    role,
    exp: claims.exp,
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  return session
}

export function logout(): void {
  localStorage.removeItem(STORAGE_KEY)
}

export function getSession(): Session | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    const session: Session = JSON.parse(raw)
    if (!session.exp || session.exp * 1000 < Date.now()) {
      localStorage.removeItem(STORAGE_KEY)
      return null
    }
    return session
  } catch {
    localStorage.removeItem(STORAGE_KEY)
    return null
  }
}
