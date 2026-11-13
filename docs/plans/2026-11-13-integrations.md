# Plan: links to more tools (Jira, Confluence, Figma, …) in one uniform way

Status: planning. Nothing here is implemented yet.

## The question

Should ccdeck add Jira, Confluence, Figma, GitLab, Slack, Sentry and others one at a time, or support most of them the same way?

**Answer: the same way, as data.** Almost everything ccdeck knows about a link comes from three signals that look alike for every tool. Only one small part differs between tools (turning a bare key like `PROJ-42` into a URL), and that part can be data too.

## What ccdeck sees today, and how it handles it

| Signal | Example | Today |
|---|---|---|
| A URL in your prompt, Claude's reply or a tool result | `https://acme.atlassian.net/browse/PAY-12` | One regex per kind in `REF_RES`: artifact, Notion, Figma, Google Docs |
| An MCP tool call and its JSON result | `mcp__atlassian__getJiraIssue` → `{"key": "PAY-12", "fields": {"summary": …}}` | Special code for Linear (`"linear" in name`), plus "creating" tools by name hints |
| A bare key in the branch or text | `pay-12-fix-refunds`, "see PAY-12" | Linear only: team keys learned from Linear URLs, workspace learned the same way |

All three are generic, except that the Linear-only parts are hard-coded. Jira, GitHub Issues, Shortcut and YouTrack keys look exactly like Linear's (`ABC-123`). They differ only in which URL a key turns into.

## Design: a provider registry

Each tool becomes one entry of data:

```python
PROVIDERS = [
  {"id": "jira", "name": "Jira", "kind": "ticket",
   "url": r"https://(?P<site>[\w-]+\.atlassian\.net)/browse/(?P<key>[A-Z][A-Z0-9]+-\d+)",
   "key_url": "https://{site}/browse/{key}",          # bare key -> link, once a site is learned
   "mcp": ["atlassian", "jira"],                       # MCP server names that belong to it
   "fields": {"key": ["key"], "title": ["fields.summary", "summary", "title"], "url": ["url", "self_html"]}},
  {"id": "confluence", "name": "Confluence", "kind": "doc",
   "url": r"https://(?P<site>[\w-]+\.atlassian\.net)/wiki/spaces/[\w~-]+/pages/(?P<id>\d+)(?:/(?P<slug>[\w+%-]+))?",
   "mcp": ["atlassian", "confluence"], "fields": {"title": ["title"], "url": ["_links.webui", "url"]}},
  {"id": "figma", "name": "Figma", "kind": "design",
   "url": r"https://(?:www\.)?figma\.com/(?:design|file|board|slides|make)/(?P<id>\w+)(?:/(?P<slug>[\w-]+))?", "mcp": ["figma"]},
  ...
]
```

One generic engine then does what the code does today for Linear, for every provider:
1. **URLs:** match every provider's `url` pattern in prompts, replies and tool results. The title comes from the slug when there is one, otherwise it's filled in later.
2. **MCP tools:** the server part of `mcp__<server>__<tool>` picks the provider. Its JSON results are read with the provider's `fields` paths (key, title, URL). That's how titles appear for links that have no readable slug.
3. **Keys:** a bare key counts when its prefix (team or project) was seen in a real URL of a ticket provider. It then becomes that provider's link through `key_url`. This is today's Linear rule, generalized. It also settles which tool owns a prefix: `PAY` seen in a Jira URL means `PAY-12` is Jira, and `ENG` seen in a Linear URL means `ENG-7` is Linear. A prefix seen in both is shown without a link instead of guessing.
4. **Source and primary:** the 0.4.4 rules (first prompt, branch, created by the session) are already per link. They apply unchanged.
5. **Display:** chips and drawer sections are grouped by **kind**, not by tool:

   | Kind | Shown as | Providers |
   |---|---|---|
   | ticket | "Ticket" | Linear, Jira, GitHub Issues, GitLab issues, Shortcut, Asana, ClickUp, Monday, YouTrack, Sentry issues |
   | doc | "Pages and documents" | Notion, Confluence, Google Docs, Sheets and Slides, Coda, Quip, SharePoint and OneDrive, Dropbox Paper, Claude artifacts |
   | design | "Designs" | Figma, FigJam, Miro, Excalidraw, Whimsical |
   | code | "Pull requests" | GitHub PRs, GitLab MRs, Bitbucket PRs |
   | chat | "Threads" | Slack, Teams, Discord message links |

   Icons are per kind, plus the provider's name in text. The page's CSP doesn't allow loading logos from other sites, and we shouldn't ship other companies' logos anyway.

**Your own tools.** `~/.claude/ccdeck/providers.json` takes the same entries, for self-hosted Jira, GitLab or an internal tracker. A user then adds a tool without a release:

```json
[{"id": "acme-jira", "name": "Jira", "kind": "ticket",
  "url": "https://jira\\.acme\\.internal/browse/(?P<key>[A-Z][A-Z0-9]+-\\d+)",
  "key_url": "https://jira.acme.internal/browse/{key}"}]
```

The regex patterns come from a file the user writes. They're compiled with a timeout guard (patterns are checked on load and run per line), and a bad pattern is skipped with a warning, not a crash.

## What stays per-tool

Two things still differ between tools, and both are optional:
- **Live state**, the way `gh` gives PR states today. The generic engine shows links and titles only. Live state for a provider needs that tool's API or CLI and the user's login. Candidates in order: GitLab MRs (`glab mr view`, the same shape as `gh`), Jira status (`jira` CLI or REST with a token), Linear status (API key). Each is a small adapter with one function: `state(link) -> {state, title}`. It's off unless its CLI or token is found.
- **Special URL shapes**, like Notion's title-plus-id slug or Google's `/d/<id>/edit`. These are a `title` function on the provider. It's one line of code, not a new integration.

## Which tools, in which order

Ordered by how often they show up in developer sessions and how much we gain:

1. **Refactor first, with no visible change.** Move artifact, Notion, Figma, Google Docs and Linear into the registry. All current tests must pass unchanged. This step proves the design.
2. **Atlassian:** Jira and Confluence, with Cloud URL patterns and the Atlassian MCP server's field names.
3. **GitHub Issues and GitLab:** issues and MRs. GitLab MRs also count as PRs, with live state from `glab`.
4. **Google Sheets and Slides, Miro, Slack threads, Sentry issues.** These are pattern-only.
5. **`providers.json`** for user-defined tools, with a README section and examples.
6. **Live state adapters:** GitLab first, then Jira.

## Tests

- A table-driven test per provider: sample URLs (with and without slugs), a sample MCP result, and a sample branch name, each with its expected key, title, kind and URL.
- Key ownership: a prefix seen in Jira URLs goes to Jira, a Linear prefix goes to Linear, a prefix seen in both gets no link, and "UTF-8" stays nothing.
- A bad `providers.json` (invalid regex, wrong types) is skipped with a warning.

## Open questions

1. Show the provider name ("Jira") or only the kind ("Ticket") on cards? The plan says the kind on the section, and the provider name on the chip.
2. Should a session have one primary ticket across all trackers, or one per tracker (for example a Jira ticket for the customer and a Linear ticket for engineering)? The plan allows several primaries, ordered by source.
3. Is Sentry an "issue" (ticket kind), or its own "error" kind with a different icon?
