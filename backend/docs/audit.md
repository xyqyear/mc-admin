# Operation Audit (`app.audit`)

Starlette middleware that records every state-changing HTTP request to a JSON log. Built so a self-hoster can reconstruct "who did what when" without standing up a separate auditing service.

## Why a middleware, not per-handler logging

State-changing operations are scattered across dozens of routers. Forgetting to log one is the default failure mode. A middleware that fires on `POST | PUT | PATCH | DELETE` (configurable) catches everything by construction; new endpoints are audited automatically with no opt-in.

## What gets logged

For each matched request:

- `timestamp` (UTC, ISO-8601)
- `method`, `path`, `status_code`, `processing_time_ms`
- User context: `user_id`, `username`, `role` — extracted from the JWT bearer if present
- `client_ip` — `X-Forwarded-For` or `X-Real-IP` if set, otherwise the socket peer
- `request_body` — JSON-decoded if the body is `application/json` and within `max_body_size`. Larger payloads are skipped (logged as `null`) to avoid blowing up the log file.

Output is one JSON object per line via `TimedRotatingFileHandler` (midnight rotation, UTF-8). Log path: `<settings.logs_dir>/<settings.audit.log_file>`.

## Sensitive-field masking

Configured by `settings.audit.sensitive_fields`. The middleware walks the decoded body recursively; any key whose lowercase name contains a sensitive substring (default set: `password`, `token`, `secret`, `key`) has its value replaced with `"***"`. This applies to nested dicts and lists of dicts — important for endpoints that nest credentials in provider configs.

## Why we read the body in the middleware

FastAPI consumes the request body once. The middleware reads it eagerly, then re-injects it via `Request._receive` so downstream handlers see it normally. Body reads happen *before* the handler runs, so even a 500 still gets the body audited.

## Configuration

```toml
[audit]
enabled = true
log_file = "operations.log"
max_body_size = 65536        # bytes
methods = ["POST", "PUT", "PATCH", "DELETE"]
sensitive_fields = ["password", "token", "secret", "key"]
```

## File

- `audit.py` — `OperationAuditMiddleware`. Wired in `app.main` ASGI stack between CORS and the API sub-app.
