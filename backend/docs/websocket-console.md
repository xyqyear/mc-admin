# Console WebSocket (`app.websocket.console`)

Real-time bidirectional terminal access to a running server's container. The frontend's xterm.js attaches to this WebSocket; the server attaches to the Docker container's stdio via a docker-py *attach socket*, so input/output go directly through the container's pseudo-TTY — no log file polling, no `mc-send-to-console` shim.

## Why docker-py attach (not docker logs)

Reading `docker logs` and writing to a side channel was the old approach. It has two problems: log rotation can drop lines, and there's no way to write *to* the server's stdin (so command history, tab completion, RCON-style inputs don't work). `docker attach` exposes the container's stdio as a single bidirectional socket — the same thing `docker attach <id>` does on the CLI. We just bridge it to a WebSocket.

## Connection lifecycle

Frontend opens a WebSocket at `/api/servers/{server_id}/console?cols=<c>&rows=<r>`. The browser sends the session cookie during the WebSocket handshake. The handler:

1. Accepts the WebSocket.
2. Resolves the `MCInstance`. If the server doesn't exist or isn't running, sends an error message and closes.
3. Opens a docker-py attach socket: `APIClient(unix://var/run/docker.sock).attach_socket(container_id, params={stdin:1, stdout:1, stderr:1, stream:1})`.
4. Sets the underlying socket non-blocking; reads via `loop.sock_recv(socket._sock, 4096)`, writes via `loop.sock_sendall(socket._sock, data.encode())`.
5. Spawns a read loop that forwards container output to the client.
6. In the main loop, processes incoming WebSocket messages until disconnect.

On disconnect (either side), cancels the read task, closes the docker socket, closes the docker client.

## Message protocol

JSON in both directions.

**Server → client**:

- `{"type": "log", "content": "..."}` — terminal output (history on connect, then live stream)
- `{"type": "info", "content": "..."}` — non-fatal status (e.g. "container restarting")
- `{"type": "error", "message": "..."}` — fatal; connection will close

**Client → server**:

- `{"type": "input", "data": "..."}` — raw stdin bytes (so arrow-key escapes, Ctrl-C, tab, etc. all work)
- `{"type": "resize", "height": int, "width": int}` — terminal resize

## History on connect

Before the live stream starts, the handler fetches `docker.logs(container_id, tail=HISTORY_LOG_LINES)` and emits the result as `log` messages. This populates the xterm scrollback so the user can see what was happening before they connected.

## Auth

The handler authenticates the WebSocket from the HttpOnly session cookie and validates the `Origin` header against the current host (with localhost dev origins allowed). Token query params are not accepted.

## No backend reconnection

The backend doesn't try to reconnect to the docker socket if it drops — the WebSocket simply closes. The frontend's `useServerConsoleWebSocket` hook owns reconnection (exponential backoff, capped retries).

## File

- `websocket/console.py` — `ConsoleWebSocketHandler`
