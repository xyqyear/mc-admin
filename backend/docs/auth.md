# Authentication (`app.auth`)

Browser authentication uses a JWT stored in an HttpOnly cookie, paired with a readable CSRF cookie. The master token remains a header-only operational credential for non-browser/system flows such as verifying a WebSocket login code.

## Session JWT

`auth/jwt_utils.py` handles signing and password hashing:

- **Signing**: HS256 via `joserfc` with `OctKey(settings.jwt.secret_key)`.
- **Hashing**: Argon2 via `pwdlib`.
- **Expiry**: `settings.jwt.access_token_expire_minutes` (default 30 days).

`auth/session.py` defines the browser session contract:

- `mc_admin_session` — HttpOnly JWT cookie scoped to `/api`
- `mc_admin_csrf` — readable CSRF cookie scoped to `/`
- `X-CSRF-Token` — required header for unsafe cookie-authenticated requests
- Claims include `sub`, `user_id`, `username`, `role`, `created_at`, `csrf`, and `exp`.

`get_current_user` (in `app.dependencies`) reads the session cookie, validates the JWT, and returns a `UserPublic`. It also accepts `Authorization: Bearer <master_token>` for operational calls. `RequireRole(UserRole.OWNER)` is the role guard.

## Password Login

`POST /api/auth/token` accepts the OAuth2 password form fields and sets both auth cookies on success. The response body is `{user}` so the frontend can seed its `GET /api/user/me` query cache without receiving the JWT.

`POST /api/auth/logout` clears both cookies.

## CSRF

`CSRFMiddleware` checks unsafe methods when a session cookie is present. The CSRF header must match both the readable CSRF cookie and the CSRF claim in the JWT. Login, logout, code-login completion, and master-token calls are exempt.

## Master Token

`settings.master_token` is a long secret stored in `config.toml`. It bypasses the normal browser session check when sent as `Authorization: Bearer <master_token>`. Treat it like a root password.

## WebSocket-Code Login

Designed for "I'm sitting at a new browser, I don't want to type my password — let me confirm from my phone".

`auth/login_code.py` — `LoginCodeManager`:

1. Browser opens a WebSocket to `/api/auth/code`.
2. Backend generates an 8-digit numeric code, stores it against the WebSocket id, sends `{"type": "code", "code": "...", "timeout": 60}`.
3. Browser shows the code.
4. On a second device, the user submits the code through `POST /api/auth/verifyCode` using the master token.
5. The backend validates the user and code, creates a short-lived one-time ticket, and sends `{"type": "verified", "ticket": "..."}` through the waiting WebSocket.
6. The browser calls `POST /api/auth/code/complete` with the ticket; that HTTP response sets the HttpOnly session cookie and returns `{user}`.

Codes rotate every 60 s if not consumed (`rotate_code_loop`). Completion tickets expire after 5 minutes and are single-use.

## Roles

`UserRole.ADMIN` — standard. `UserRole.OWNER` — full admin including user management. The seed `OWNER` is created on first start; subsequent users come from the user-management UI.

## Files

- `jwt_utils.py` — JWT minting + password hashing
- `session.py` — cookie/session helpers, CSRF middleware, auth extraction
- `login_code.py` — `LoginCodeManager` (WebSocket code flow)
