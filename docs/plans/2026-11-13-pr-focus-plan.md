# Plan: a focus plan for open PRs

Status: planning. Nothing here is implemented yet.

## Goal

A view that answers "what should I do next?" across all your open PRs. It puts each PR into one of a few numbered **steps** (merge, fix, review, wait, clean up), shows what has to happen next, and who has to do it: you, or a named Claude session you can message (`@checkpoint-96`).

The idea comes from a hand-made "Checkpoint open work" dashboard that Claude put together from session reports. That one needed AI to decide priorities. This version uses **no AI**: only PR statuses from GitHub and what ccdeck already knows about sessions. The AI summaries plan (`2026-11-13-ai-summaries.md`, PR #17) can improve the order and the next-step text later (see "Later, with AI").

## Which PRs: the scope setting

There are three scopes, picked with a control at the top of the view. The choice is remembered in the browser, using the dashboard's existing `localStorage` store.

| Scope | PRs |
|---|---|
| **From sessions** (default) | PRs that a session in ccdeck owns: it created the PR, or the PR's branch is the session's branch. This is the `own` flag in `pr_details()`. |
| **All mine** | Every open PR you authored, from any repo, whether or not a session made it. |
| **Mine and reviews** | All mine, plus open PRs by others where your review is requested or you have already reviewed. |

A PR that you authored but no session owns shows "—" in the Session column. That is useful in its own right: it shows work without a live owner.

Cloud sessions that open PRs as the Claude GitHub app aren't "authored by you" on GitHub. Those belong to the cloud sessions plan (PR #22) and aren't covered here.

## Getting the data: one GraphQL search per scope

`gh search prs` can't return CI, review or conflict state (it has no `statusCheckRollup`, `reviewDecision` or `mergeable` field). Calling `gh pr view` for each PR works, but takes one call per PR. A GraphQL `search` returns everything in one call per query. I checked it on 2026-11-13: 15 open PRs, cost 2 points.

```
gh api graphql -f q='is:pr is:open author:@me archived:false' -f query='
query($q: String!, $after: String) {
  search(type: ISSUE, query: $q, first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      url number title isDraft createdAt updatedAt headRefName
      repository { nameWithOwner } author { login }
      reviewDecision mergeable
      commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
      reviewThreads(first: 100) { nodes { isResolved } }
    } }
  }
}'
```

- **Queries.** Each scope needs at most three: `author:@me`, `review-requested:@me` and `reviewed-by:@me`. The last two drop PRs you authored.
- **Paging.** Follow `pageInfo.endCursor` until `hasNextPage` is false. Stop after 5 pages, and show that the list was cut off.
- **Unknown merge state.** `mergeable` is `UNKNOWN` while GitHub is still computing it. Treat that as unknown, not as a conflict, and fetch again on the next cycle.
- **No CI.** No `statusCheckRollup` means the repo has no checks, which is shown as "no CI". It doesn't block a merge.
- **Unresolved review comments.** These are the number of `reviewThreads` with `isResolved: false`. Bot reviews (CodeRabbit, Gemini) count too, because they are often what is still left to do.
- **Refresh and failure.** The daemon fetches every 3 minutes, and at once when you press "Refresh". It only fetches when `gh` is installed, and not with `CCDECK_PR_PLAN=0`. It saves the result to `~/.claude/ccdeck/pr-plan.json`, as `reviews.json` is saved today. This replaces `fetch_review_requests()`, which then reads its list from the same file. If `gh` fails, the last result stays on screen with its age.
- **Session PRs.** The PRs that sessions already track (the `pr-cache.json` entries) are matched to search results by URL. In the "From sessions" scope a session's PR may not be authored by you. Those PRs keep using `fetch_pr()`.

## The steps

Each PR goes into the first step whose rule it matches. Each step lists its PRs oldest first, by `updatedAt`, so work that has been sitting longest comes up first.

| Step | Rule | Next step text | Who |
|---|---|---|---|
| **1. Merge** | Not a draft, CI passing or no CI, merge state `MERGEABLE`, review `APPROVED` or none required, no unresolved threads | "Merge it" | You |
| **2. Fix** | CI failing, merge conflict, `CHANGES_REQUESTED`, or unresolved threads | One line per problem: "CI failing", "Rebase: conflicts with main", "3 unresolved review comments" | The owning session if it is running (`@name`), otherwise you |
| **3. Review** | Someone else's PR that requests your review and that you haven't reviewed since its last push | "Review it" | You |
| **4. Waiting** | CI pending, or waiting for a review from someone else | "CI running" / "Waiting for review from …" | Nobody (shown smaller) |
| **5. Clean up** | A draft, or no activity for 14 days | "Draft: finish or close" / "Stale for 23 days: close or pick up" | You |

Step 1 comes first because those are quick wins, and merging often unblocks other PRs. Step 2 comes before reviews because a PR that you and your sessions own and that is stuck blocks your own work.

A PR you have already reviewed, with no new commits since, goes to step 4 and waits for the author.

## What a row shows

PR (repo, number, title, linked), CI, review state, unresolved comments, step text, who acts, session (`@name`, short id, its ccdeck state, running or not), the main Linear issue (from the session's `linear_list`), and age.

Above the steps are count tiles: open PRs, ready to merge, to fix, review requests, and waiting on you. Those use the same "needs you" logic as the step rules, so the numbers match the lists.

## Where it lives in the dashboard

It's a second view next to the session list ("Sessions | PRs"), with the same filter box, so a search for a repo, branch or `@name` narrows both. The details panel for a session opens from the Session column.

The rule function is a small pure function, `pr_step(pr, session) -> (step, texts, who)` in `ccdeck`, so `ccdeck list` can print the same plan in the terminal (`ccdeck prs`).

## Tests

- A table test for `pr_step()`, with one case per rule and the order between rules. Examples: failing CI and approved goes to Fix, a draft with failing CI goes to Fix, `UNKNOWN` merge state doesn't go to Fix.
- Parsing of a saved GraphQL response: paging, a missing `statusCheckRollup`, and PRs you authored being dropped from the review queries.
- The scope filter: "From sessions" only includes `own` PRs; "Mine and reviews" doesn't include the same PR twice.

## Not in the first version

- **Superseded or duplicate PRs** (#23 made obsolete by #24, for example). Without AI, the only safe signal is two open PRs from the same session touching the same files. Leave it out at first.
- **Priorities within a step** beyond age (P0 or P1). Linear priority could come from the Linear integration later.
- **Sending a message to the owning session** from the dashboard ("Ask @checkpoint-96 to fix CI"). The name is shown, and copying a ready-made message is a small follow-up.

## Later, with AI

Once session summaries exist (PR #17), they can:
- order PRs within a step by what actually blocks what;
- replace the generic next step text with a specific one ("CodeRabbit wants the teleport id fixed; one-line change");
- group PRs by goal ("Ship 0.7.4") instead of only by status;
- flag superseded PRs.

The no-AI step stays the fallback when there are no summaries.
