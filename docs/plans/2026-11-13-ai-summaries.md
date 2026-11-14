# Plan: AI summaries of sessions

Status: planning. Nothing here is implemented yet.

## Goal

When you come back to a session, you shouldn't have to scroll its transcript to remember what it was about. ccdeck should show three summaries, each answering one question:

| Level | Question | Where it shows | Length |
|---|---|---|---|
| 1. Last message | What did Claude just say? | Card and row, instead of the cut-off raw text | One sentence |
| 2. Recent steps | What happened in the last turn? | Card (on hover or expand), drawer | 3–5 bullets |
| 3. Whole session | Why does this session exist, and where is it? | Top of the drawer | A short structured brief |

The level 3 brief has fixed fields:
- **Goal:** why the session was started and what "done" looks like.
- **Status:** how it's going, in one or two sentences, with blockers.
- **Done so far:** the main steps completed.
- **Next steps:** what Claude or you do next.
- **Still missing:** steps that the goal needs but nobody has started, such as tests, docs, a PR, review or deploy.

## How to call a model

**Default: `claude -p` with Haiku, on the user's own login.** Most ccdeck users have Claude Code on a subscription and no API key. ccdeck runs headless Claude Code on the condensed transcript:

```
claude -p --model haiku --output-format json --max-turns 1 [tools disabled] < prompt
```

- It needs no key or extra setup, and it uses the same account and provider the session already uses.
- Usage counts against the user's plan limits. That's why summaries are opt-in, capped and cheap (see Limits).
- **The spike must check:**
  - the exact flags for "no tools" and "no MCP servers", and for not loading the project's CLAUDE.md;
  - the cold-start time;
  - whether `--output-format json` gives the text and the usage.

**Fallback: the Messages API directly** when `ANTHROPIC_API_KEY` is set. It's one `urllib` POST, so it needs no SDK, and it's faster than starting `claude`. Default model: the current Haiku.

**Two traps with `claude -p`:**
1. **Its own transcript.** Each run writes a transcript to `~/.claude/projects/`, and ccdeck would list it as a session. Run it with `cwd` set to `~/.claude/ccdeck/summarizer/`, and skip that project folder when scanning.
2. **Hooks.** The run fires ccdeck's own hooks. Set `CCDECK_HOOKS=0` in its environment, and have `ccdeck hook` exit at once when that's set.

## What the model sees

The input is a condensed transcript, not the raw JSONL:
- **Your prompts:** in full, up to 2,000 characters each.
- **Claude's text replies:** in full for the last turn, the first 600 characters for older ones.
- **Tool calls:** one line each, such as `Bash: npm test`, `Edit: src/a.ts` or `create_pull_request → #42`. Tool results are left out, except errors (first line only).
- **The session's own ticket, pages and PRs** with their titles (from the 0.4.4 primary links), and the PR states.

**Budget:** about 30k input tokens. A longer session is condensed head-and-tail: the first prompts set the goal, the recent turns set the status. The level 3 brief is also incremental. The model gets the previous brief plus the events since it was written, and returns an updated brief. Long sessions then don't get more expensive over time.

**Output:** JSON with a fixed schema, validated before it's saved. Invalid output is retried once and then dropped.

```json
{"last": "…", "recent": ["…"], "goal": "…", "status": "…", "done": ["…"], "next": ["…"], "missing": ["…"]}
```

## When it runs

**Daemon-side.** A single worker thread works through a queue, one job at a time. Hooks only enqueue (they write a marker file). They never call a model, so a session never waits for a summary.

| Trigger | Levels |
|---|---|
| `Stop`, when the last message is longer than about 300 characters | 1 and 2 |
| `Stop`, when the session has 3 or more new prompts since the last brief, or 30 minutes have passed | 3 |
| `SessionEnd`, or the session moving to Closed | 3, if anything changed since the last brief |
| **Summarize** button in the drawer | 3, now |

Nothing runs for sessions that are done or parked, or older than the listing window.

**Cache.** Summaries are saved in `~/.claude/ccdeck/summaries/<session>.json`. Each one records the transcript size and last entry it was made from, the model, and its token usage. A summary is stale when the transcript has grown since. The UI shows its age ("summary from 12 min ago") and never hides the raw message.

## Limits, cost, privacy

- **Off by default.** Turn on with `ccdeck summaries on`, a toggle in the dashboard (which needs a confirmation), or `CCDECK_SUMMARIES=1`. The setting lives in `config.json`, next to the approvals flag.
- **Caps:** at most one job at a time, at most N per hour (default 30), and a daily token budget (default 500k input tokens). The dashboard shows today's usage.
- **Model:** Haiku by default, `CCDECK_SUMMARY_MODEL` to change it.
- **Privacy:** the condensed transcript goes to the same provider the session already talks to, through the same login. Nothing goes to any other service. The README says this plainly next to the switch.

## UI

- **Card:** the level 1 sentence replaces the raw message preview. A small "AI" mark shows on it, and the tooltip shows the raw text. "Read the full message" still opens the drawer.
- **Drawer:** a **Summary** section at the top shows Goal, Status, Next steps and Still missing, with Done so far collapsed. It has a "Regenerate" button and the summary's age. The raw last message stays below it.
- **Needs you panel:** the level 1 sentence goes above the raw message. The exact permission command always shows raw, never summarized.

## Work plan

1. **Spike (half a day):**
   - `claude -p` flags, cold start, JSON output, usage;
   - confirm the transcript and hook traps, and the fixes for both;
   - compare the quality of Haiku and Sonnet on five real sessions.
2. **Condenser:** a function from transcript to condensed text, with unit tests on fixtures (budget, head-and-tail, tool lines).
3. **Worker:** queue, `claude -p` and API back ends, schema validation, cache, caps, config flag. Tests use a fake `claude` on `PATH`, like the fake `gh`.
4. **Triggers:** the hook marker files and the Stop, SessionEnd and button rules.
5. **UI:** card line, drawer section, regenerate, usage display, toggle.
6. **Docs:** README section on cost and privacy.

## Open questions

1. Is Haiku good enough for the level 3 brief, or should the brief use Sonnet while levels 1 and 2 use Haiku?
2. Should "Still missing" use the repository's conventions, for example "this repo needs a CHANGELOG entry"? That means reading CLAUDE.md, so more tokens.
3. Should summaries also feed state detection, for example a better "Decision needed" than the `?` heuristic? It's tempting, but it makes states depend on an opt-in feature.
4. Default caps: are 30 jobs per hour and 500k tokens per day right for a subscription user?
