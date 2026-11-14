# ccdeck

[![CI](https://github.com/slonik923/ccdeck/actions/workflows/ci.yml/badge.svg)](https://github.com/slonik923/ccdeck/actions/workflows/ci.yml)

Keep track of your **local Claude Code sessions** on Linux and macOS. It answers four questions:

- Which sessions are open?
- Which ones need you, and for what?
- Which ones produced a PR, an artifact or a document?
- Which ones are done?

You get a live dashboard in the browser at `http://localhost:7799`, served by a small background service. There is also a terminal list. Desktop notifications tell you when a session starts waiting on you.

![Dashboard](docs/dashboard.png)

`ccdeck` is one Python 3.9+ file plus one HTML page, using only the standard library. It reads the transcripts Claude Code already writes to `~/.claude/projects/` and never modifies them. PR states come from the GitHub CLI (`gh`) when it's installed.

## Install

### As a Claude Code plugin (recommended)

In Claude Code:

```text
/plugin install ccdeck --marketplace slonik923/ccdeck
```

On Claude Code older than 2.1.275, run `/plugin marketplace add slonik923/ccdeck` first, then `/plugin install ccdeck@ccdeck`. Restart Claude Code or run `/reload-plugins`.

That's all. When a session starts, the plugin's hooks:
- record each session's live state (working, waiting for permission, finished, closed);
- start the dashboard in the background if it isn't already running.

Open it at `http://localhost:7799`, or with `/ccdeck:dashboard`.

For PR states, also install the GitHub CLI (`sudo apt install gh` on Ubuntu, `brew install gh` on macOS) and run `gh auth login`.

The plugin adds these commands to Claude Code:

| Command | What it does |
|---|---|
| `/ccdeck:dashboard` | Opens the dashboard in your browser, starting it first if it isn't running |
| `/ccdeck:install` | Adds the background service (the dashboard starts at login) and the `ccdeck` terminal command |
| `/ccdeck:done [note]` | Marks the current session done, with an optional note |
| `/ccdeck:park [note]` | Sets the current session aside for later |

`/ccdeck:install` copies ccdeck to `~/.local/share/ccdeck`, and the service and command run from that copy. Nothing points at the plugin's versioned cache folder.

**Updates.** After a plugin update, the next session's hooks report the new version, and the running dashboard restarts itself on it within a few seconds; an open dashboard tab reloads too. The header and the footer show the version that is running. (Dashboards older than 0.4.3 can't do this yet: restart once with `/ccdeck:install`.)

### From a clone (always-on service, `ccdeck` command)

To get the `ccdeck` terminal command and have the dashboard running from login, even before you open Claude Code:

```bash
git clone https://github.com/slonik923/ccdeck.git ~/ccdeck
~/ccdeck/ccdeck install            # add --no-hooks if you also use the plugin
```

`install` does four things:

1. **Command.** It links `~/.local/bin/ccdeck` to the script in the clone, so `git pull` updates it.
2. **Hooks.** It adds the same hooks to `~/.claude/settings.json`, after saving a backup as `settings.json.bak-ccdeck`. Skip this with `--no-hooks` when you use the plugin. Having both is harmless: a duplicate event is ignored.
3. **Background service.** On Linux it adds a systemd user service, `ccdeck.service`. On macOS it adds a launchd agent, `~/Library/LaunchAgents/io.github.slonik923.ccdeck.plist`. The service starts at login, restarts if it crashes, keeps PR states up to date and sends the notifications.
4. **App launcher** (Linux only). It adds a **ccdeck** entry that opens the dashboard. On macOS, run `ccdeck open` or bookmark the page.

On macOS, `~/.local/bin` may not be on your `PATH`. `install` tells you if it isn't.

Options: `--port 8123`, `--no-hooks`, `--no-service`. To remove everything: `ccdeck uninstall`. Your marks and notes stay in `~/.claude/ccdeck/`.

## The dashboard

The page is laid out to answer "what needs me?" first:
- **Needs you** is a queue, oldest first, next to a focus panel. The panel shows the selected session in full: Claude's message and the exact command it wants to run.
- **PRs to fix** are cards.
- Everything else is a compact row, with actions in a menu (or the keyboard).
- The strip of lines under the header has one line per session, coloured by its state.

Click a card or row, or press Enter, for the detail drawer: the full message, resume command, PRs, links, files, tokens, and your note. The actions menu has **Details** too. The page is dark only.

Sessions are grouped by what they need from you. The dashboard refreshes every 2 seconds. The browser tab title and icon show how many sessions need you.

The groups say what you have to do, most urgent first:

| Group | State | Meaning |
|---|---|---|
| 🔴 **Needs you** | Permission needed | A tool call is waiting for your approval |
| | Question for you | Claude asked a multiple-choice question (`AskUserQuestion`) |
| | Plan to approve | Claude wrote a plan and waits for approval (`ExitPlanMode`) |
| | Decision needed | Claude's last message ends with a question or asks you to choose |
| | Error | The last turn ended with an API error |
| 🟣 **PRs to fix** | CI failing | A check failed on one of the session's PRs |
| | Changes requested | A reviewer asked for changes |
| | PR has conflicts | The PR can't merge cleanly |
| 🟢 **Your turn** | PR approved, merge it | The session's PRs are approved and green |
| | Draft PR, review it | The PR is a draft: look it over yourself, then mark it ready |
| | Finished, your turn | Claude finished, and the session is open and waiting for your next prompt |
| | Quiet, interrupted? | The last state was "working", but nothing has happened for 15 minutes |
| 🟡 **In progress** | Working | Claude is running right now |
| | CI running | The PR's checks are still running |
| | Waiting for review | The PR is ready and green, and waits on reviewers |
| ⚪ **Set aside** | Parked | You set the session aside |
| | Closed / Closed mid-task | The process has exited and you haven't marked the session done |
| ✅ **Done** | PR merged | All of the session's PRs are merged |
| | Done | You marked it done (hidden by default) |

"In progress" means someone else is on it: Claude, CI or your reviewers. A PR waiting for review counts as in progress, because you can't approve your own (or your agent's) PR.

**Review requests.** PRs where a colleague asked for your review aren't part of any session, so they get their own list on the dashboard (and in `ccdeck`), refreshed every 5 minutes with `gh search prs --review-requested=@me`. Your own sessions' PRs are left out. To turn it off, set `CCDECK_REVIEW_REQUESTS=0`.

Each card shows:
- the title, folder, branch and number of prompts
- **token usage**: a bar showing how full the context window is, plus output and input tokens. Subagents are included, and hovering shows the breakdown, including cache reads
- the last message: Claude's reply, the permission request, or your own prompt (click it to expand)
- the session's own PRs, with their live state
- its Linear ticket and pages: the ones it started from or created (artifacts, Notion, Figma, Google Docs)
- the files the session wrote

**The session's own things versus the rest.** A PR belongs to the session when the session created it, or when the PR's branch is the session's branch. A ticket or page belongs to it when it's in the session's first prompt, in the branch name (Linear), or the session created it. These are what cards show, and what decides the PR state. Tickets, PRs and pages the session only looked up or mentioned are listed in the details under **Also touched**. A long last message has a "Read the full message" link to the details.

Each card has these buttons:
- **Resume ▸** opens a new terminal window in the session's folder and runs `claude --resume <id>`.
- **Copy cmd** copies that same command.
- **Folder** opens the session's folder in the file manager.
- **↻ PRs** re-checks the PR states now.
- **Park**, **Note** and **Done ✓** set your own marks on the session.

Keyboard: `/` jumps to the filter box, `j` / `k` move between sessions, `Enter` opens the details, `r` resumes, `.` opens the actions menu (then `C` `O` `R` `P` `N` `D`), and `Esc` closes whatever is open.

The terminal used for **Resume ▸**:
- **On macOS:** iTerm if it's installed, otherwise Terminal. Set `CCDECK_TERMINAL=terminal` or `iterm` to choose.
- **On Linux:** the first one found from GNOME Terminal, Ptyxis, Console, Konsole, xfce4-terminal, Tilix, kitty, Alacritty and xterm.

Any other terminal works through `CCDECK_TERMINAL`, for example `CCDECK_TERMINAL="wezterm start --"`. macOS asks once whether ccdeck may control Terminal or iTerm.

## Terminal

```text
ccdeck                 sessions grouped by state, then review requests (done ones and closed ones older than 14 days are hidden)
ccdeck -a              everything
ccdeck show 3          details: PRs with state, links, files, last messages
ccdeck resume 3        cd into the folder and claude --resume
ccdeck done 3 [note]   mark solved             ccdeck undone 3
ccdeck park 3          set aside               ccdeck unpark 3
ccdeck note 3 text     attach a note
ccdeck open            open the dashboard
ccdeck serve           run the dashboard in the foreground (instead of the service)
```

`3` is the row number from the last list. A prefix of the session id also works.

## How it works

- **Transcripts.** `~/.claude/projects/*/*.jsonl` provides each session's title, folder, branch and messages, plus the PR, artifact and document links Claude posted or created, and the files it wrote. Parsing is cached by file size and modification time.
- **Hooks.** The hooks (`SessionStart`, `UserPromptSubmit`, `PostToolUse`, `Notification`, `Stop`, `SessionEnd`) write a small state file for each session to `~/.claude/ccdeck/state/`. That's how the tool knows exactly whether a session is working, waiting for permission or finished. The file also records the Claude process, so a crashed session isn't shown as running. Without hooks, these states are guessed from running `claude` processes and the end of each transcript.
- **PR states.** `gh pr view` is called for PRs in sessions that aren't done. Open PRs are re-checked every 3 minutes, and every minute while CI is running.
- **The server** listens only on `127.0.0.1`. The API needs a random token, stored in `~/.claude/ccdeck/token`, which only the dashboard page receives. Requests whose `Host` header isn't localhost are rejected. Together, these stop other websites from reading your sessions or opening terminals.
- **Token usage** comes from the `usage` that Claude Code saves with each response. Each response is counted once, even though it's saved on several entries. The context bar uses the size of the latest request against the model's window: 1M for current models, 200K for Claude Haiku 4.5 and older models. To use a different limit, set `CCDECK_CONTEXT_LIMIT`. Tokens are shown rather than dollars, because many people use Claude Code on a subscription and prices differ by model.
- **Dashboard autostart.** With the plugin, the `SessionStart` hook starts `ccdeck serve` in the background when nothing answers on the port; it logs to `~/.claude/ccdeck/serve.log`. It doesn't do this when the systemd service or launchd agent is installed. To turn it off, set `CCDECK_AUTOSTART=0`.
- **Notifications** appear when a session moves into *Needs you*, *PRs to fix* or *Your turn*. They use `notify-send` on Linux and Notification Center (through `osascript`) on macOS. To turn them off, set `CCDECK_NOTIFY=0`.
- **Running or closed.** A session counts as running in one of two ways:
  - **Reported by hooks:** its hooks recorded the Claude process, and that process is still alive with the same start time.
  - **Guessed:** for sessions no hook has reported on (for example, ones started before you installed the plugin), N `claude` processes in a folder mark that folder's N most recent sessions as open. A `claude --resume <id>` process marks exactly that session.

  The details drawer shows which way it was decided.
- **Linear, Notion and artifacts.** Links count when you paste them in a prompt, when Claude mentions them, or when a tool creates them. Titles come from the tool results or from the page's URL.
  - Linear tickets also come from the branch name (Linear's `you/eng-42-title` format), from Linear tool calls, and from plain mentions like "ENG-42".
  - A branch name or plain mention counts only when its team key has appeared in a real Linear URL somewhere, or is listed in `CCDECK_LINEAR_TEAMS=ENG,OPS`. So "UTF-8" isn't taken for a ticket.
  - The workspace for links is learned the same way; you can also set it with `CCDECK_LINEAR_WORKSPACE`.
- **Processes.** On Linux, ccdeck reads `/proc`. On macOS it takes one `ps` snapshot per refresh and uses `lsof` for working folders. A process's start time is compared too, so a reused pid isn't mistaken for a live session.

## Limits

- Only **local** sessions are covered. Cloud sessions are listed at claude.ai/code.
- "Decision needed" is a heuristic: the last paragraph ends with `?` or contains phrases such as "should I" or "do you want".
- Links are collected from Claude's own messages and from the results of tools that create things. URLs Claude only read are not included.

## Development

```bash
python3 -m unittest discover -s tests -v
```

The tests run against a throwaway `HOME` with synthetic transcripts and a fake `gh`.

**Screenshots for PRs.** `scripts/demo_data.py` writes a demo `HOME` of made-up sessions, so you can run any version of ccdeck on the same data: `HOME=/tmp/demo PATH=/tmp/demo/bin:$PATH python3 ccdeck serve --port 7800`. PRs that change the dashboard show it before and after on that data; `CLAUDE.md` has the details.

**AI review.** Pull requests get automatic reviews from Gemini Code Assist and CodeRabbit (both free for public repos). Their settings are in `.gemini/` and `.coderabbit.yaml`, and the rules they review against are in `.gemini/styleguide.md`. Ask for a re-review with `/gemini review` or `@coderabbitai review`.

**Merging into `main`** needs all of these:
- the CI jobs pass;
- every review conversation is resolved, so an open comment (critical or not) blocks the merge;
- the **AI review gate** check passes (`.github/workflows/ai-review.yml`): CodeRabbit isn't requesting changes, and Gemini has reviewed the PR;
- the **CodeRabbit** check passes, which means CodeRabbit has reviewed the latest commit. Gemini reviews when a PR opens; comment `/gemini review` to ask again after bigger changes.

The rules are in `.github/rulesets/main.json`. GitHub applies them only after they're imported once, under Settings → Rules → Rulesets → New ruleset → Import a ruleset.

**Releasing.** Claude Code updates an installed plugin only when the `version` in `.claude-plugin/plugin.json` changes. Bump it, and `VERSION` in `ccdeck` with it, in every release; CI checks that the two match. Users then get it by running `/plugin marketplace update ccdeck` and updating ccdeck from the `/plugin` menu (or reinstalling it).

## License and affiliation

MIT, see `LICENSE`. ccdeck is an independent project and is not affiliated with or endorsed by Anthropic. "Claude" and "Claude Code" are trademarks of Anthropic.
