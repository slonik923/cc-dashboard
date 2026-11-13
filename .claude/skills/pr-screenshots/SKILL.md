---
name: pr-screenshots
description: Use when a ccdeck change touches the dashboard (web/, or anything that changes what the page shows) and before asking for review: take before/after screenshots on made-up demo data, highlight what changed, check them, and add them to the PR description.
---

# PR screenshots for ccdeck

Every PR that changes what the dashboard shows gets screenshots in its description: the base branch next to this branch, on the same made-up demo data, with the changed parts boxed and labelled. The reviewer should see what changed without running anything.

## 1. Write a spec for this change

Put a spec in `scripts/shots/<topic>.json`. Each shot names a view, the steps to reach it, and **what to highlight: only what this PR changed.** Format (all keys but `name` optional):

```json
{ "shots": [
  { "name": "board", "width": 1440, "height": 1000, "full": true, "scale": 1,
    "highlight": [ { "sel": "#h-reviews", "label": "New: review requests" } ] },
  { "name": "details", "steps": [ { "click": ".nf-q[data-nav='d-queue']" },
                                  { "click": ".nf-actions button:has-text('Details')", "wait": 500 } ],
    "clip": ".drawer", "highlight": [ { "sel": ".drawer .dsec.related", "label": "Also touched" } ] }
] }
```

- **Steps:** `click`, `press` (a key), `hover`, `scroll` (into view) and `wait` (ms).
- **`clip`:** shoots one element instead of the page.
- **Labels** are short and say what's new or different ("New: …", "Moved", "Now says …").
- **Data:** the demo sessions come from `scripts/demo_data.py`. Their ids are `d-deploy`, `d-auth`, `d-queue`, `d-flaky`, `d-csv`, `d-rate`, `d-pdf`, `d-node`, `d-dark`, `d-cache`, `d-badges`, `d-bun` and `d-tz`. If the change needs a case the data doesn't have, add a session there, in the same PR. The data is invented: never put real names, repos or tickets in it.
- **Selectors:** cards and rows have `data-sid`, the Needs-you queue buttons have `data-nav`, and pills have `data-g` (group) and `data-k` (state).

## 2. Take them

```bash
scripts/pr-shots.sh scripts/shots/<topic>.json            # this working tree vs origin/main
HEAD_REF=origin/<branch> scripts/pr-shots.sh spec.json origin/main   # another branch
```

The script:
- starts the base version and this version of `ccdeck serve` on free ports, on copies of the same demo HOME, with a fake `gh`;
- writes `.shots/after/` (with highlights), `.shots/before/` (no highlights; steps whose target doesn't exist yet are skipped) and `.shots/compare/` (before and after side by side);
- fails when a highlight or step selector matches nothing in "after", or when the page logs an error. Fix the spec or the bug; don't loosen the check.

It needs Node with Playwright. In Claude Code cloud sessions `require("playwright")` already works. Locally, run `npm i -g playwright && npx playwright install chromium`.

## 3. Look at every image before posting

Open each PNG with the Read tool. Check that:
- each highlight sits on the right element;
- "before" really shows the old state;
- nothing private shows (it shouldn't: the data is made up).

If a picture doesn't show the change clearly, change the spec and run again.

## 4. Attach them to the PR

```bash
CCDECK_REPO=slonik923/ccdeck scripts/upload-shots.sh <pr-number> .shots/compare/board.png .shots/after/details.png
```

- **Where they go:** the images are pushed to the orphan branch `screenshots`, under `pr-<n>/<sha>/`, so `main` stays clean and every run gets new URLs.
- **What it prints:** Markdown with `raw.githubusercontent.com` links.
- **The PR:** put that Markdown in a `## Screenshots` section of the PR description, updating the PR with the GitHub tools, with one line per image saying what to look at.
- **Which images:** use the `compare/` image for whole-page views, and the `after/` image when one panel is the point.

## 5. When the change can't be seen

If the PR changes nothing visible, skip this skill and say so in the PR ("No UI change").
