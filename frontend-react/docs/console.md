# Server Console

Real-time terminal at `/server/{id}/console`. Bridges xterm.js in the browser to the Docker container's pseudo-TTY through a backend WebSocket. Command history, tab completion, arrow-key navigation, and Ctrl-C / Ctrl-V all work the same way they would in `docker attach <id>` — those features come from the Minecraft server / Docker TTY itself, not from us.

## Why xterm.js + raw stdio

Earlier versions read `latest.log` via HTTP polling and used `mc-send-to-console` for input. That works but loses every interactive feature: no scrollback control, no command history, no tab completion. xterm.js plus a docker-py attach socket on the backend gives a fully interactive terminal with no extra mechanism.

## Page composition

```
pages/server/servers/ServerConsole.tsx
└─ PageHeader (server state tag, start/stop/restart buttons, status line)
└─ ServerTerminal (xterm.js viewport)
```

The page header reuses `ServerOperationButtons` so the user can stop/start a stuck server without leaving the console.

## `ServerTerminal.tsx`

Owns the xterm.js `Terminal` instance directly and loads two addons:

- **FitAddon** — sizes the terminal to the container; refits on window resize and on prop changes.
- **WebLinksAddon** — makes URLs in output clickable.

10k-line scrollback, 14px Consolas font (`font-family: Consolas, monospace`).
The component imports the xterm CSS, opens the terminal into its container, observes container resizes, and disposes the terminal, addons, subscriptions, and observer on unmount.

Imperative ref API:

- `clear()`, `write(text)`, `fit()`, `getSize()`
- `onMessage(message)` — writes incoming WebSocket messages to the terminal

Incoming JSON message types:

- `log` — raw bytes, written verbatim
- `info` — cyan-prefixed status (e.g. "container restarting")
- `error` — red-prefixed; usually precedes a close

## `useServerConsoleWebSocket`

The hook owns the connection lifecycle and is the *only* place that talks to the WebSocket. The page calls `sendInput(data)` and `sendResize(rows, cols)`; the hook turns these into `{type: "input", data}` / `{type: "resize", height, width}` JSON.

Connection states: `DISCONNECTED → CONNECTING → CONNECTED | ERROR`.

**Reconnection**: exponential backoff `[1, 2, 4, 8, 16] s`, max 5 retries. Triggered on unexpected close; not triggered on user-initiated close. The retry timer is cleared on cleanup so navigating away cancels pending reconnects.

**Auth**: the browser sends the HttpOnly session cookie during the WebSocket handshake. Cols/rows are URL params so the backend can size the docker attach properly on first byte.

## Lifecycle

- Mount → `ServerTerminal` opens xterm; `ServerConsole` connects the WebSocket after the terminal reports its size
- Window resize / drawer toggle → `term.fit()` → `sendResize(rows, cols)`
- Keyboard input → xterm `onData` → `sendInput(data)`
- Unmount → dispose terminal resources, close WebSocket, and clear retry timer

## Files

- `pages/server/servers/ServerConsole.tsx`
- `components/server/ServerTerminal.tsx`
- `hooks/useServerConsoleWebSocket.ts`
