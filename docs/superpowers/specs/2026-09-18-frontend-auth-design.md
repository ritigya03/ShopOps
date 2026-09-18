# Frontend Auth — design

Status: approved by user
Date: 2026-09-18
Scope: first of 4 decomposed frontend sub-projects (auth → chat wiring → approvals wiring → dashboard wiring). This one only.

## What this replaces

`shop-ops-ai-frontend/app/page.tsx` currently fakes login (`Login` component just navigates on click, no real check) and fakes role (`useState<Role>` toggled by a role-switcher dropdown in the sidebar). Everything else in the frontend (chat, approvals, dashboards) still runs on mock data — out of scope here.

## Decisions

- **Auth call:** raw `fetch` POST to Cognito's `InitiateAuth` (`USER_PASSWORD_AUTH`), no AWS SDK dependency. Same flow the backend's `verify_cognito_tokens.py` already uses.
- **Token storage:** `localStorage`. Simplest option for a pure client-side SPA with no Next.js server routes today.
- **Expiry:** no refresh-token flow. On expiry (checked via the ID token's `exp` claim, or a 401 from the backend) — clear storage, redirect to `/login`.
- **Roles:** frontend adopts the real Cognito groups as-is: `Viewer | SupportAgent | OperationsManager` (drops the mock `admin`, adds `Viewer`). When `cognito:groups` has multiple entries, pick one by the same priority the backend uses (`app/auth.py`'s `_ROLE_PRIORITY`): OperationsManager > SupportAgent > Viewer.
- **Role switcher removed:** role now comes from who logged in, not a toggle. Replaced with a read-only "signed in as \<email\> · \<role\>" display + a real Sign out action.

## New files

- `lib/auth.ts` — `login(email, password)`, `logout()`, `getSession()` (reads/validates `{idToken, email, role, exp}` from `localStorage`, returns `null` if missing/expired).
- `lib/api.ts` — `apiFetch(path, options)`: attaches `Authorization: Bearer <idToken>`, calls `${NEXT_PUBLIC_API_BASE_URL}${path}`; on 401, clears session and redirects to `/login`. This is the shared entrypoint the later 3 sub-projects will import.
- `.env.local` (gitignored):
  ```
  NEXT_PUBLIC_COGNITO_REGION=ap-south-1
  NEXT_PUBLIC_COGNITO_USER_POOL_ID=ap-south-1_XcUY5aCda
  NEXT_PUBLIC_COGNITO_APP_CLIENT_ID=2hhav02cbsal51628q4js0c3jk
  NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
  ```

## Modified files

- `lib/mock-data.ts` — `Role` type → `'Viewer' | 'SupportAgent' | 'OperationsManager'`; `navItems`/`roles` relabeled. Sellers + Approvals stay `OperationsManager`-only (matches real `can_view_seller_metrics`/`can_approve_compensation`); Dashboard/Chat/Orders visible to all three roles.
- `app/page.tsx` — real session check on mount (no session → force `/login`); `Login` calls `lib/auth.login()`, shows inline error on `NotAuthorizedException`; sidebar role-switcher replaced per above.

## Testing

No test infra in the frontend yet. Manual verification: `pnpm dev`, log in as each of the 3 real Cognito test users (`viewer-test@example.com`, `support-test@example.com`, `manager-test@example.com` — passwords in the backend `.env`), confirm correct nav visibility per role, confirm logout + expired-token both bounce to `/login`.
