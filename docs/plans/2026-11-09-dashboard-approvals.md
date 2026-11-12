# Plan: approve permission prompts from the dashboard

Status: planning. Nothing here is implemented yet.

## Goal

When a session stops on a permission prompt ("Claude needs your permission to use Bash: npm run deploy"), the dashboard card shows exactly what Claude wants to run. You can **Allow** or **Deny** it there, without switching to that terminal. The terminal dialog keeps working as before, and the first answer wins.

This is for your own machine. To approve from your phone, Claude Code's **Remote Control** already forwards permission prompts to the Claude app with push notifications ("Push when actions required" in `/config`). ccdeck's value is the overview across all sessions on the desktop, not replacing that.

## What the spike showed (Claude Code 2.1.321)

The docs don't say whether the terminal dialog waits for a `PermissionRequest` hook. I measured it with a hook that logs and waits, in an interactive session under tmux:

| Test | Result |
|---|---|
| Hook started, waits 20 s | The dialog appeared **0.56 s** after the hook started, while the hook was still waiting. The dialog doesn't wait for the hook. |
| Answered "Yes" in the terminal while the hook waited | The command ran **80 ms** later. The hook was **not** killed; it kept running to its end, and its (empty) output was ignored. |
| Hook printed `{"decision":{"behavior":"allow"}}` after 5 s, dialog open | The dialog closed and the command ran **0.15 s** later. |

So a blocking `PermissionRequest` hook is a second, parallel way to answer the same prompt. A slow or absent answer never delays the terminal. The one thing to handle is a hook that keeps waiting after the terminal already answered (see "Knowing a request is over").

From the docs:
- **Output and input.** The hook's output is `hookSpecificOutput.decision`: `{behavior: "allow", updatedInput?, updatedPermissions?}` or `{behavior: "deny", message?, interrupt?}`. Its input has `tool_name`, `tool_input`, `permission_suggestions` and `mcp_server`, but no `tool_use_id`.
- **Rules still apply.** A matching deny rule still wins over a hook's allow.
- **Timeout.** The default is 600 s; we'll set our own. When it's reached, the hook is cancelled and its output discarded.
- **Headless runs.** In sessions that can't prompt (`-p`, background subagents), no decision means deny. So ccdeck could also approve headless runs; we keep that in mind but don't build it first.
- **No `async`.** `async: true` hooks can't decide, so the hook has to block.

## Design

### 1. The hook waits for an answer

Add `PermissionRequest` to the plugin's `hooks/hooks.json` and to `ccdeck install`, with `"timeout": 1800`. When the timeout ends the wait, the terminal dialog is still there. For this event, `ccdeck hook`:

1. **Exits at once, with no output,** unless all of these hold:
   - approvals are switched on (they're opt-in; see Security);
   - the dashboard daemon is running (its heartbeat is less than 30 s old);
   - the session is interactive. To start with, approvals are skipped for `-p` sessions, where silence would mean deny.
2. **Writes a request file**, `~/.claude/ccdeck/requests/<id>.json` (mode 600). It holds: `id` (random), `session_id`, `cwd`, `tool_name`, `tool_input`, `permission_suggestions`, `permission_mode`, `created`, the hook's `pid`, and `input_hash` (sha256 of the canonical JSON of `tool_name` and `tool_input`).
3. **Polls every 0.3 s for an answer file,** `requests/<id>.answer.json`. It stops when:
   - an answer arrives: it checks that `answer.id` and `answer.input_hash` match, prints the decision JSON, and exits 0;
   - the request is marked over (next section), or the daemon disappears for more than 30 s: it exits 0 with no output;
   - the timeout is near: it exits 0 with no output.
4. **Fails closed:** any exception means no output (exit 0), so the terminal dialog stays in charge. The hook never prints an allow it didn't receive from the dashboard.

Requests and answers are files rather than HTTP. That way the hook needs no network code or token, it works the same with the systemd service or autostart, and a crashed daemon can't leave a hook stuck: the hook watches the heartbeat.

### 2. Knowing a request is over

The terminal can answer first, and the hook isn't told. The other hook events that ccdeck already receives close the session's open requests:

| Event in the same session | Meaning |
|---|---|
| `PostToolUse` or `PostToolUseFailure` with a matching `tool_name` and `input_hash` | Allowed in the terminal (or by a rule), and the tool ran |
| `UserPromptSubmit` | You typed instead. A denial in the terminal goes back to Claude, and the next thing that happens is your prompt or `Stop`. |
| `Stop` or `SessionEnd` | The turn or the session is over |
| `PermissionDenied` | Auto mode denied it |

The hook process for that event marks matching requests as `over` by writing `requests/<id>.over`. The waiting hook sees that and exits; the daemon drops the request from the dashboard. One gap remains: a request answered in the terminal whose tool then runs for a long time stays shown until `PostToolUse` fires. The card could say "may already be answered in the terminal" once the session's last transcript entry is newer than the request.

`PostToolUseFailure` and `PermissionDenied` must be added to the hook events we listen to.

### 3. Daemon and API

- **Daemon.** It reads `requests/*.json` on each 2 s scan. That's fast enough for a human, and the hook polls the answer file itself. It attaches open requests to their sessions in `/api/sessions`. The session's state is already "Permission needed"; the card gains the request.
- **`POST /api/action`** gets `{action: "approve" | "deny", id, request_id, input_hash, message?}`. It writes the answer file atomically (write to a temp file, then rename). It refuses if the request is over, gone, or its hash differs. The usual checks still apply: the token, a localhost `Host` header, and JSON only.
- **Decision log.** Each decision is appended to `~/.claude/ccdeck/approvals.log` (time, session, tool, short input, decision, who: dashboard or notification).

### 4. Dashboard UI

The "Permission needed" card shows the request in full, not just the one-line notification:
- **Bash:** the command, in monospace, with its `description` if present.
- **Edit / MultiEdit:** the file path and a small diff of old versus new.
- **Write:** the path, size and the first lines.
- **WebFetch / WebSearch:** the URL or query.
- **MCP tools:** the server, the tool name, and the arguments as formatted JSON.
- **Other tools:** the input as formatted JSON.

Buttons:
- **Allow** (primary);
- **Deny**, with an optional reason sent to Claude as `message`;
- later, **Allow and don't ask again**, built from `permission_suggestions` (sent as `updatedPermissions`).

Allow on a Bash command is a confirm step, not one click: a second click on "Allow `rm -rf …`?" within 5 s. The keyboard has no shortcut that approves.

If a session has several open requests (rare: parallel tool calls), they're shown oldest first.

### 5. Notifications (phase 2)

On Ubuntu 22.04 and later, `notify-send --action=allow=Allow --action=deny=Deny --wait` shows buttons and prints the one clicked. The daemon can run one per request and write the answer like the dashboard does, so a prompt can be answered from the notification itself. The fallback is a plain notification that opens the dashboard.

## Security

Approving from a browser tab means a web page can make your machine run commands, so:

- **Opt-in.** Approvals are off until you turn them on: `ccdeck approvals on`, a toggle in the dashboard (which needs the CLI or a confirmation), or `CCDECK_APPROVALS=1`. The setting lives in `~/.claude/ccdeck/config.json`.
- **Localhost only, protected like today's actions:**
  - the server binds 127.0.0.1;
  - the `Host` header must be localhost, against DNS rebinding;
  - a per-install token that only the served page knows, against CSRF;
  - `Content-Type: application/json`, which forces a CORS preflight.
- **No phone access.** Exposing the dashboard on the LAN is out of scope; use Remote Control for that.
- **Bound decisions.** Each decision is tied to one request id and its `input_hash`, so an answer can't apply to a different command than the one shown.
- **Hook fails closed.** Any error leaves the decision to the terminal. A deny rule in settings still beats an allow.
- **Private files.** Request and answer files are created with mode 600, in a directory with mode 700.

## Work plan

1. **Hook protocol** (`ccdeck`):
   - the `PermissionRequest` branch;
   - request and answer files;
   - the polling loop and its exits;
   - marking requests over from the other events;
   - the new events in `HOOK_EVENTS` and `hooks/hooks.json`;
   - the config flag.
   - Unit tests: the hook as a subprocess with a fake answer, a fake `PostToolUse`, a dead daemon and a timeout.
2. **Daemon and API:** read requests, the `approve`/`deny` actions with hash checks, and the decision log. Tests against the test server.
3. **Dashboard:** the request view for each tool, the buttons, the confirm step for Bash, and the approvals toggle.
4. **End-to-end script** `scripts/e2e-permission.sh`: the spike above, made repeatable with tmux. It runs locally, not in CI, because CI has no logged-in Claude Code. Cases:
   - dashboard allow;
   - dashboard deny with a reason;
   - terminal answer first, where the hook must exit and the card disappear;
   - two sessions at once.
5. **Notification actions** (phase 2), **"don't ask again"** (phase 2), and a decision on headless `-p` approvals (phase 3).
6. **Docs:** a README section with the security notes and how to turn it on and off.

## Open questions

1. Should approvals be on by default once the plugin is installed? This plan says no, keep it opt-in.
2. Is the 1800 s hook timeout right? An abandoned prompt keeps one idle `python3` process for up to 30 minutes, about 10 MB.
3. Should "Deny" offer `interrupt: true` (stop Claude) next to a plain deny?
4. Headless `-p` runs: worth supporting as "approve your CI/background agents from the dashboard"?
