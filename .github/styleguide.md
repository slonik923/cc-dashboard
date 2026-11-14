# ccdeck review guide

Used by CodeRabbit (`.coderabbit.yaml` points it here). Humans welcome too.

ccdeck is a local dashboard for Claude Code sessions: one Python script (`ccdeck`), a page (`web/index.html`, `web/ccdeck.css`), Claude Code plugin files (`.claude-plugin/`, `hooks/`, `skills/`) and tests (`tests/test_ccdeck.py`). It runs on Linux and macOS.

## What matters most

1. **Hooks must never get in Claude Code's way.**
   - `ccdeck hook` runs on every session event, so it must exit 0 quickly.
   - It must never raise past `cmd_hook`, and never print anything Claude Code would act on.
   - The only exception is the opt-in `PermissionRequest` approval path. It must fail closed: on any error, no output, and the terminal decides.
2. **Standard library only, Python 3.9+.**
   - No third-party imports, no syntax newer than 3.9 (e.g. no `match`, no `X | Y` type unions at runtime).
   - The page loads nothing from other origins.
3. **The local server is an attack surface.**
   - It binds `127.0.0.1` and requires the token on API calls.
   - It rejects non-localhost `Host` headers (DNS rebinding).
   - Actions accept JSON only.
   - Flag any change that weakens these, opens terminals or files with unchecked input, or builds shell commands without quoting (`shlex.quote`, AppleScript string escaping).
4. **The page builds DOM nodes; it never uses `innerHTML` with data.**
   - Transcript text, PR titles and links are untrusted.
   - Links must be `http(s)` and open with `rel="noopener noreferrer"`.
   - The CSP allows only `'self'` scripts and `'self' 'unsafe-inline'` styles.
5. **Both platforms.**
   - Process detection has a `/proc` path (Linux) and a `ps`/`lsof` path (macOS, also forced by `CCDECK_NO_PROC=1`), and changes must handle both.
   - Paths can be symlinked (macOS `/var` → `/private/var`), so compare resolved paths.
   - Shell scripts must run on bash 3.2 (macOS), so no associative arrays.
6. **Never modify Claude Code's files.**
   - Transcripts in `~/.claude/projects` are read-only to ccdeck.
   - `settings.json` is changed only by `install`/`uninstall`, with a backup.
7. **Releases:** `VERSION` in `ccdeck` and `version` in `.claude-plugin/plugin.json` change together (CI checks it). A user-visible change needs a version bump, or installed plugins won't update.

## Conventions

- **Tests:** new behaviour gets a test in `tests/test_ccdeck.py`. Tests run against a throwaway `HOME` with a fake `gh`, and must not touch the real `~/.claude`, the network or a real terminal.
- **Demo data** (`scripts/demo_data.py`) is invented and gets published in PR screenshots: no real names, repos, tickets or URLs.
- **UI:** the page is dark only. Use the CSS custom properties (`--text`, `--g`, …) rather than raw colours, and keep the keyboard shortcuts working.
- **Docs:** user-facing behaviour is documented in `README.md` in plain language.

## Less important

Style nits that a formatter would catch, naming preferences, and "consider adding a docstring" on small private helpers. Mention them only if they hide a real problem.
