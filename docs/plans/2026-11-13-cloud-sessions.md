# Plan: cloud sessions (Claude Code on the web) in ccdeck

Status: planning. Nothing here is implemented yet.

## Goal

Sessions that run in the cloud (claude.ai/code, the Claude app, sessions started from Slack or a GitHub Action) should show up in ccdeck next to local ones. Each should show its title, repository and branch, its PRs, and a link to open it. Where we can tell, it should also show whether it needs you. **Resume** should work for these sessions too.

## What we can and can't see (checked with Claude Code 2.1.323)

| Source | What it gives | Usable? |
|---|---|---|
| Local transcripts (`~/.claude/projects`) | Nothing about cloud sessions, until you pull one down with `claude --teleport <id>`; then it's a local transcript | Already works for teleported sessions |
| `claude --teleport` with no id | An interactive picker of your cloud sessions | Not scriptable. It's a TTY picker with no `--json` |
| `claude agents --json` | Live sessions **on this machine** (`pid`, `cwd`, `sessionId`, `kind`, `status: busy`/…) | Not cloud sessions, but a big win for local ones (see "Side benefit") |
| The API the claude.ai app and `--teleport` use | Everything: title, status, waiting for input | **Undocumented.** It would mean reading Claude Code's login token and calling a private API. It can break at any time, and it handles the user's credentials. Not for now. |
| GitHub | Cloud sessions push a branch and usually open a PR. The PR description (and often the commit trailer) links the session: `https://claude.ai/code/session_…` | **Yes.** Public, stable, and already used by ccdeck through `gh` |

So there's **no supported API to list cloud sessions today**. GitHub is the honest source: it covers every cloud session that has pushed work, which is the part you come back to.

## Design

### Phase 1: discover cloud sessions through GitHub

Every 5 minutes, in the same loop as the review requests:

```
gh search prs --author=@me --state=open --json number,title,url,body,headRefName,repository,updatedAt,isDraft --limit 100
gh search prs --author=@me --state=closed --merged --json … --limit 30   # recently merged, to mark them done
```

- **Finding the session:** the session id comes from `claude.ai/code/session_<id>` in the PR body. When it isn't there, ccdeck looks for a `Claude-Session:` trailer on the head commit (`gh api repos/{repo}/commits/{sha}`, only for PRs whose body has no link).
- **Grouping:** one cloud session can open several PRs, so a cloud session is a group of PRs with the same session id.
- **Which PRs count:** PRs authored by you or by the Claude GitHub app, under your account's repos. `CCDECK_CLOUD=0` turns this off, the same as review requests.

**What a cloud session shows:**
- **Title:** the first PR's title, until a better source exists.
- **Repository and branch** come from the PR. The **state** comes from its PRs with the same rules as local sessions: PRs to fix, Your turn (draft or approved), In progress (CI or review), Done (merged).
- **Running or not:** unknown. The card says "Cloud" instead of "Running" or "Not running".
- **Needs you:** unknown. A cloud session that waits on a question shows up in the Claude app and on your phone, and ccdeck can't see it. The card says so in its tooltip.
- **Actions:**
  - **Open** opens `https://claude.ai/code/session_<id>` in the browser.
  - **Teleport ▸** opens a terminal in the matching local clone and runs `claude --teleport <id>`. The clone is found from the `cwd` of local sessions whose git remote is that repository. If there's none, the action copies the command.
  - **Park**, **Note** and **Done** work like they do for local sessions. Marks are keyed by session id.

**Where they show:** cloud sessions go into the same groups as local ones, with a small cloud mark on the pill and a **Local / Cloud / All** filter. They aren't a separate list: the whole point of the groups is "what do I have to do", wherever the session runs.

**Teleported sessions.** When a cloud session is teleported, a local transcript appears with the same session id. ccdeck merges the two into one entry: the local data (live state, messages) plus the cloud link.

### Phase 2: richer state from GitHub

Cloud sessions answer review comments and CI on their own PRs, and leave comments with the attribution footer. From the PR timeline (`gh pr view --json comments,reviews`), ccdeck can show the last thing the session or a reviewer said, and when. That gives a card a "last message" even without the transcript. It costs one extra `gh` call per open cloud PR every few minutes. It's opt-in if that's too much.

### Phase 3: an official source, when one exists

Keep the cloud part behind one small interface: `list_cloud_sessions() -> [{id, title, repo, branch, url, status?, waiting?}]`. Today it's backed by GitHub. If Claude Code adds a scriptable listing (for example `claude --teleport --list --json`), a second backend plugs in and fills the fields GitHub can't: status and "waiting for you". ccdeck won't call private APIs or read Claude Code's tokens.

## Side benefit for local sessions: `claude agents --json`

`claude agents --json` prints every live session on the machine (interactive and background) with its `sessionId`, `pid`, `cwd` and `status`. That's exactly what the "Running or closed" guesswork tries to work out from process lists. Today a guessed session can show as Closed while it's open; this tells ccdeck directly. Plan:
- Call it once per scan (it takes about 1 s, so cache it for 5 s). Use it as the first source for "running", before the hook pid and the `ps` guess.
- Use `status` (busy) as a "working" signal for sessions without hooks.
- Fall back to today's logic when the command is missing (older Claude Code) or fails.

This is worth doing first, independently of cloud sessions. It's small and fixes a real annoyance.

## Work plan

1. **`claude agents --json` as the liveness source** (local, small). Tests use a fake `claude` on `PATH`.
2. **Cloud discovery through GitHub:** search, the session link and trailer parser, grouping, the cache file, the `CCDECK_CLOUD` flag. Tests use the fake `gh`.
3. **UI:** cloud mark, Local/Cloud filter, Open and Teleport actions, the unknown-state tooltip, and the drawer. Screenshots go through the pr-screenshots skill, with cloud sessions added to the demo data.
4. **Merging teleported sessions** with their cloud entry.
5. **Phase 2 timeline** (optional).
6. **Docs:** README section on what's visible and what isn't, and why.

## Open questions

1. Should cloud sessions without any PR (still working, or only talked) show at all? GitHub can't see them. The plan says no, until there's an official listing.
2. Include PRs authored by the Claude GitHub app in repos you own but didn't open yourself (for example sessions a colleague started in your repo)? The plan says only sessions whose PRs you authored, or that link a session on your account. We can't tell the account from the link, so that means "authored by you" in practice.
3. The search covers all repos `gh` can see. Should there be an allow-list (`CCDECK_CLOUD_REPOS=owner/*`) for people with many orgs?
