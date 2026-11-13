#!/usr/bin/env python3
"""Write a demo HOME full of made-up Claude Code sessions, for screenshots and manual checks.

    python3 scripts/demo_data.py /tmp/ccdeck-demo [--pid PID]

Then run any version of ccdeck against it:

    HOME=/tmp/ccdeck-demo PATH=/tmp/ccdeck-demo/bin:$PATH python3 ccdeck serve --port 7800

Nothing here is real: names, repos, tickets and PRs are invented, so screenshots are safe to
publish. `--pid` is a process that stays alive while you take screenshots (the sessions with hook
state count as running while it lives). A fake `gh` in <home>/bin answers PR and review queries.
"""
import argparse
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = "https://github.com/acme/{}/pull/{}"
WORK = "/home/demo/code/"


def ts(minutes_ago):
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return t.isoformat().replace("+00:00", "Z")


def text(t):
    return {"type": "text", "text": t}


def tool(tid, name, inp=None):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp or {}}


class Session:
    def __init__(self, home, sid, title, repo, branch, prompt, m):
        self.sid, self.cwd, self.branch, self.n = sid, WORK + repo, branch, 0
        self.path = home / ".claude" / "projects" / ("-home-demo-code-" + repo) / f"{sid}.jsonl"
        self.entries = []
        self.user(prompt, m)
        self.entries.append({"type": "ai-title", "aiTitle": title})

    def _base(self, kind, m):
        return {"type": kind, "cwd": self.cwd, "gitBranch": self.branch, "timestamp": ts(m), "sessionId": self.sid}

    def user(self, content, m):
        e = self._base("user", m)
        e["message"] = {"role": "user", "content": content}
        self.entries.append(e)
        return self

    def say(self, blocks, m, ctx=150000, out=8000, **extra):
        self.n += 1
        e = self._base("assistant", m)
        e["message"] = {"id": f"{self.sid}-m{self.n}", "role": "assistant", "model": "claude-opus-5-5", "content": blocks,
                        "usage": {"input_tokens": 3, "cache_creation_input_tokens": ctx // 10,
                                  "cache_read_input_tokens": ctx - ctx // 10, "output_tokens": out}}
        e.update(extra)
        self.entries.append(e)
        return self

    def result(self, tid, content, m):
        return self.user([{"type": "tool_result", "tool_use_id": tid, "content": content}], m)

    def created_pr(self, repo, n, m):
        tid = f"pr{n}"
        self.say([tool(tid, "mcp__github__create_pull_request", {"title": "PR"})], m)
        return self.result(tid, json.dumps({"url": REPO.format(repo, n)}), m)

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            for e in self.entries:
                f.write(json.dumps(e) + "\n")


FAKE_GH = r'''#!/usr/bin/env python3
import json, sys
PRS = __PRS__
if sys.argv[1:3] == ["search", "prs"]:
    print(json.dumps(__REVIEWS__)); sys.exit(0)
if sys.argv[1:3] == ["pr", "view"]:
    url = sys.argv[3]
    d = PRS.get(url)
    if not d:
        print("not found", file=sys.stderr); sys.exit(1)
    print(json.dumps(d)); sys.exit(0)
if sys.argv[1:3] == ["auth", "status"]:
    sys.exit(0)
sys.exit(1)
'''


def pr(n, title, state="OPEN", draft=False, review="", checks="SUCCESS", mergeable="MERGEABLE", head=""):
    roll = [] if checks is None else [{"status": "IN_PROGRESS" if checks == "PENDING" else "COMPLETED",
                                       "conclusion": "" if checks == "PENDING" else checks}]
    return {"number": n, "title": title, "state": state, "isDraft": draft, "reviewDecision": review,
            "mergeable": mergeable, "statusCheckRollup": roll, "headRefName": head}


def build(home, pid):
    home = Path(home)
    S = lambda *a: Session(home, *a)  # noqa: E731
    sessions = [
        S("d-deploy", "Ship Stripe webhook handler to staging", "billing-api", "feat/stripe-webhooks", "deploy it to staging", 3)
        .say([text("The webhook handler is finished and all 212 unit tests pass. To check signature handling against real "
                   "Stripe events, I want to deploy to staging and replay the last 50 events."),
              tool("b1", "Bash", {"command": "npm run deploy -- --env=staging"})], 2, ctx=391000, out=48200),
        S("d-auth", "Migrate auth to Lucia v4", "web-app", "chore/lucia-v4", "migrate auth", 6)
        .say([tool("q1", "AskUserQuestion", {"questions": [{"question": "Should sessions created before the migration be "
                                                                         "invalidated, or should I write a shim that upgrades them?"}]})], 5),
        S("d-queue", "Pick a queue for transactional email", "notifications", "dana/eng-57-email-queue",
          "Pick a queue for https://linear.app/acme/issue/ENG-57/transactional-email-queue, spec in "
          "https://www.notion.so/acme/Email-queue-spec-" + "c" * 32, 12)
        .say([tool("l1", "mcp__linear__get_issue", {"id": "ENG-31"})], 12)
        .result("l1", json.dumps({"identifier": "ENG-31", "title": "Old SMTP retries", "url": "https://linear.app/acme/issue/ENG-31"}), 12)
        .say([text("## Two options for the email queue\n\n| | BullMQ | pg-boss |\n|---|---|---|\n| Infra | Redis (**already running**) | Postgres only |\n"
                   "| Peak throughput | ~5k jobs/s | ~800 jobs/s |\n\n1. **BullMQ**: faster, one more moving part.\n2. **pg-boss**: no new infra.\n\n"
                   "Which one should I implement?")], 11, ctx=134000),
        S("d-flaky", "Fix flaky e2e checkout test", "storefront", "fix/checkout-flake", "fix the flake", 15)
        .say([text("API Error: 529 Overloaded. The session stopped after 3 retries while running Playwright.")], 14, isApiErrorMessage=True),
        S("d-csv", "Add CSV export to reports", "dashboard", "feat/csv-export", "csv export", 20)
        .created_pr("dashboard", 212, 19)
        .say([text("Opened PR #212. Typecheck fails because ReportRow.total is optional, and the e2e download step times out. "
                   "I'll look at both next unless you want something else.")], 18, ctx=301000),
        S("d-rate", "Rate-limit the public API", "billing-api", "feat/rate-limit", "rate limit ENG-38", 35)
        .created_pr("billing-api", 88, 34).say([text("Pushed the rate limiter; review asked for a per-key override.")], 34),
        S("d-pdf", "Refactor invoice PDF renderer", "billing-api", "refactor/pdf-renderer", "refactor the renderer", 1)
        .say([tool("e1", "Edit", {"file_path": WORK + "billing-api/src/pdf/layout.ts"})], 0, ctx=156000),
        S("d-node", "Bump Node to 22 LTS", "web-app", "chore/node-22", "bump node", 4)
        .created_pr("web-app", 301, 3).say([text("Pushed fixes; CI is running.")], 3, ctx=97000),
        S("d-dark", "Dark mode for the settings page", "web-app", "feat/settings-dark", "dark mode", 8)
        .created_pr("web-app", 299, 7).say([text("Opened a draft PR: theme toggle, persisted, 14 components updated. All checks pass.")], 7),
        S("d-cache", "Cache exchange rates", "billing-api", "feat/fx-cache", "cache fx rates", 50)
        .created_pr("billing-api", 90, 49).say([text("PR #90 is up and green; requested review from the payments team.")], 49),
        S("d-badges", "Update README badges", "tooling", "main", "badges", 61).say([text("Updated 4 badges and the install snippet.")], 60),
        S("d-bun", "Explore Bun for build scripts", "tooling", "spike/bun-scripts", "try bun", 2881)
        .say([text("Bun cut cold start from 1.9 s to 0.4 s; two scripts still need Node APIs.")], 2880),
        S("d-tz", "Fix timezone bug in invoices", "billing-api", "fix/invoice-tz", "fix tz", 1441)
        .created_pr("billing-api", 77, 1440).say([text("Merged.")], 1440),
    ]
    for s in sessions:
        s.write()
    prs = {
        REPO.format("dashboard", 212): pr(212, "CSV export for reports", checks="FAILURE"),
        REPO.format("billing-api", 88): pr(88, "Rate-limit public API", review="CHANGES_REQUESTED"),
        REPO.format("web-app", 301): pr(301, "Node 22 LTS", checks="PENDING"),
        REPO.format("web-app", 299): pr(299, "Settings dark mode", draft=True),
        REPO.format("billing-api", 90): pr(90, "Cache exchange rates", review="REVIEW_REQUIRED"),
        REPO.format("billing-api", 77): pr(77, "Invoice timezone fix", state="MERGED", review="APPROVED"),
    }
    reviews = [{"number": 412, "title": "Move webhooks to the event bus", "url": REPO.format("platform", 412), "isDraft": False,
                "repository": {"name": "platform", "nameWithOwner": "acme/platform"}, "author": {"login": "sam"},
                "updatedAt": ts(90)}]
    gh = home / "bin" / "gh"
    gh.parent.mkdir(parents=True, exist_ok=True)
    gh.write_text(FAKE_GH.replace("__PRS__", repr(prs)).replace("__REVIEWS__", repr(reviews)))
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)

    data = home / ".claude" / "ccdeck"
    (data / "state").mkdir(parents=True, exist_ok=True)
    start = proc_start(pid)
    live = {"d-deploy": ("permission", "Claude needs your permission to use Bash"), "d-auth": ("question", None),
            "d-queue": ("stopped", None), "d-pdf": ("working", None), "d-dark": ("stopped", None),
            "d-node": ("stopped", None), "d-cache": ("stopped", None)}
    for sid, (status, msg) in live.items():
        st = {"session_id": sid, "event": "demo", "ts": __import__("time").time() + 5, "status": status,
              "pid": pid, "pid_start": start}
        if msg:
            st["message"] = msg
        (data / "state" / f"{sid}.json").write_text(json.dumps(st))
    (data / "marks.json").write_text(json.dumps({
        "d-bun": {"parked": True, "note": "after Q4 freeze"},
        "d-node": {"note": "waiting on QA"},
    }))
    return home


def proc_start(pid):
    """The start time ccdeck records for a pid, so it sees that process as alive."""
    import importlib.machinery
    import importlib.util
    path = str(Path(__file__).resolve().parent.parent / "ccdeck")
    loader = importlib.machinery.SourceFileLoader("ccdeck_demo", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("ccdeck_demo", loader))
    loader.exec_module(mod)
    return mod.proc_start_time(pid)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("home")
    ap.add_argument("--pid", type=int, default=os.getppid(), help="a process that stays alive (default: the parent shell)")
    a = ap.parse_args()
    print(build(a.home, a.pid))
