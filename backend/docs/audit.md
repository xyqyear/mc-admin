# Operation Audit (`app.audit`)

Starlette middleware that records every state-changing HTTP request to a JSON log. Built so a self-hoster can reconstruct "who did what when" without standing up a separate auditing service.

## Why a middleware, not per-handler logging

State-changing operations are scattered across dozens of routers. A middleware that fires on `POST | PUT | PATCH | DELETE` records new endpoints without per-handler opt-in. Auditing can be disabled through configuration.

## What gets logged

For each matched request:

- `timestamp` (server-local time, ISO-8601 without an explicit offset)
- `method`, `path`, `status_code`, `processing_time_ms`
- User context: `user_id`, `username`, `role` — extracted from the session cookie or master-token header if present
- `client_ip` — `X-Forwarded-For` or `X-Real-IP` if set, otherwise the socket peer
- `request_body` — decoded JSON or form fields within `max_body_size`, with sensitive fields masked. Oversized bodies produce a size-limit marker. Undecodable, multipart and other unstructured bodies record only content type and byte count; raw request text is never logged.

Output is one JSON object per line via `TimedRotatingFileHandler` (midnight rotation, UTF-8). Log path: `<settings.logs_dir>/<settings.audit.log_file>`.

## Sensitive-field masking

The middleware walks decoded bodies recursively. A field is masked when its case-insensitive name contains a configured `sensitive_fields` substring (default `password`, `token`, `secret`, `key`) or matches a configured `sensitive_exact_fields` name (default `ak`, `sk`, `code`, `ticket`). Values are replaced with `"***MASKED***"`. Both lists are configurable; deployment-specific credentials need matching rules. Exact matching preserves ordinary `task_id` and `status_code` fields. This applies to nested dicts, lists, top-level arrays, query parameters and path parameters. Forms are decoded before masking, including repeated values and percent-encoded credentials.

The default exact names cover cloud access identifiers, secret access keys, one-time login codes and completion tickets; their sensitivity and lifetimes differ. Login code generation and expiry messages do not include the code value in ordinary application logs. Name-based masking does not inspect arbitrary credential values embedded in unrelated strings.

Uvicorn uses INFO logging in the production image. Its optional protocol DEBUG logs can include raw WebSocket frames and truncated secrets, outside this HTTP audit middleware; enabling that diagnostic mode changes the logging exposure boundary.

## Why we read the body in the middleware

The middleware reads the body before the handler runs; Starlette's cached request body lets downstream handlers read it normally. A handler failure still produces an audit entry with the masked body.

## Configuration

```toml
[audit]
enabled = true
log_file = "operations.log"
max_body_size = 65536        # bytes
sensitive_fields = ["password", "token", "secret", "key"]
sensitive_exact_fields = ["ak", "sk", "code", "ticket"]
```

## File

- `audit.py` — `OperationAuditMiddleware`. Wired in `app.main` ASGI stack between CORS and the API sub-app.
