# Authentication (`app.auth`)

JWT-based authentication with two login paths and a master-token fallback. The two paths exist because browser-only and headless flows have different ergonomics — the WebSocket-code flow lets a phone with the master token authenticate a freshly-opened browser without typing a password.

## JWT

`auth/jwt_utils.py`:

- **Signing**: HS256 via `joserfc` with `OctKey(settings.jwt.secret_key)`.
- **Hashing**: Argon2 via `pwdlib` (modern default; replaced bcrypt without compat issues since stored hashes are versioned).
- **Expiry**: `settings.jwt.access_token_expire_minutes` (default 30 days).
- **Claims**: standard `sub`, `exp`, plus `username` and `role` so request handlers don't need a DB hit on every request.

`get_current_user` (in `app.dependencies`) is the FastAPI dependency that decodes the bearer token, validates expiry, and returns a `UserPublic`. `RequireRole(UserRole.OWNER)` is the role guard.

## Password login

Standard OAuth2 password flow at `POST /api/auth/token`. Returns `{access_token, token_type}`.

## Master token

`settings.master_token` is a long secret stored in `config.toml`. It bypasses the normal user check — used for the WebSocket-code verify flow and for system operations triggered outside a browser session. Treat it like a root password.

## WebSocket-code login

Designed for "I'm sitting at a new browser, I don't want to type my password — let me confirm from my phone".

`auth/login_code.py` — `LoginCodeManager`:

1. Browser opens a WebSocket to `/api/auth/code`.
2. Backend generates an 8-digit numeric code, stores it against the WebSocket id, sends `{"type": "code", "code": "...", "timeout": 60}`.
3. Browser shows the code (and a QR code that links to the verify page).
4. On a second device, the user opens the verify page, types or scans the code, and submits with the master token.
5. `POST /api/auth/verifyCode` looks up the code, finds the WebSocket, mints a JWT for the requesting username, sends `{"type": "verified", "access_token": "..."}` back through the WebSocket and closes it.
6. The browser receives the token and stores it in `useTokenStore`.

Codes rotate every 60 s if not consumed (`rotate_code_loop`). Old codes immediately become unverifiable.

## Roles

`UserRole.ADMIN` — standard. `UserRole.OWNER` — full admin including user management. The seed `OWNER` is created on first start; subsequent users come from the user-management UI.

## Files

- `jwt_utils.py` — JWT mint/decode + password hashing
- `login_code.py` — `LoginCodeManager` (WebSocket code flow)
