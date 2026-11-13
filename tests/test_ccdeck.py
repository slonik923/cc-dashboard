"""Tests for ccdeck. Run: python3 -m unittest discover -s tests -v

Each test class gets a throwaway HOME with synthetic Claude Code transcripts and a
fake `gh` on PATH, so nothing touches your real ~/.claude.
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="ccdeck-test-"))
os.environ["HOME"] = str(TMP)
os.environ.pop("CLAUDE_CONFIG_DIR", None)
os.environ["CCDECK_NOTIFY"] = "0"
os.environ["CCDECK_AUTOSTART"] = "0"

FAKE_GH = TMP / "bin" / "gh"
FAKE_GH.parent.mkdir(parents=True)
FAKE_GH.write_text("""#!/usr/bin/env python3
import json, sys
if sys.argv[1:3] == ["search", "prs"]:
    print(json.dumps([
        {"number": 6, "title": "Colleague's change", "url": "https://github.com/me/app/pull/6", "isDraft": False,
         "repository": {"name": "app", "nameWithOwner": "me/app"}, "author": {"login": "pat"}, "updatedAt": "2026-01-01T10:00:00Z"},
        {"number": 7, "title": "Mine, reviewer added me", "url": "https://github.com/me/app/pull/7", "isDraft": False,
         "repository": {"name": "app", "nameWithOwner": "me/app"}, "author": {"login": "me"}, "updatedAt": "2026-01-01T09:00:00Z"}]))
    sys.exit(0)
url = sys.argv[3]
n = int(url.rsplit("/", 1)[1])
fixtures = {
    1: {"state": "OPEN", "isDraft": True, "reviewDecision": "", "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}]},
    2: {"state": "OPEN", "isDraft": False, "reviewDecision": "", "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "FAILURE"}]},
    3: {"state": "MERGED", "isDraft": False, "reviewDecision": "APPROVED", "mergeable": "UNKNOWN",
        "statusCheckRollup": []},
    4: {"state": "OPEN", "isDraft": False, "reviewDecision": "CHANGES_REQUESTED", "mergeable": "MERGEABLE",
        "statusCheckRollup": []},
    5: {"state": "OPEN", "isDraft": False, "reviewDecision": "", "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"status": "IN_PROGRESS", "conclusion": ""}], "headRefName": "feat/x"},
    6: {"state": "OPEN", "isDraft": False, "reviewDecision": "REVIEW_REQUIRED", "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}]},
    7: {"state": "OPEN", "isDraft": False, "reviewDecision": "APPROVED", "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}]},
}
d = dict(fixtures[n], number=n, title=f"PR {n}")
print(json.dumps(d))
""")
FAKE_GH.chmod(FAKE_GH.stat().st_mode | stat.S_IEXEC)
os.environ["PATH"] = f"{FAKE_GH.parent}:{os.environ['PATH']}"

loader = importlib.machinery.SourceFileLoader("ccdeck", str(ROOT / "ccdeck"))
spec = importlib.util.spec_from_loader("ccdeck", loader)
cc = importlib.util.module_from_spec(spec)
loader.exec_module(cc)

PROJ = TMP / ".claude" / "projects" / "-work-app"
WORK = TMP / "work" / "app"


def ts(minutes_ago):
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return t.isoformat().replace("+00:00", "Z")


def user(text, m):
    return {"type": "user", "cwd": str(WORK), "gitBranch": "feat/x", "timestamp": ts(m),
            "message": {"role": "user", "content": text}}


def asst(blocks, m, **extra):
    return dict({"type": "assistant", "cwd": str(WORK), "timestamp": ts(m),
                 "message": {"role": "assistant", "content": blocks}}, **extra)


def text(t):
    return {"type": "text", "text": t}


def tool(tid, name, inp=None):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp or {}}


def result(tid, m, content="ok"):
    return user([{"type": "tool_result", "tool_use_id": tid, "content": content}], m)


def write_session(sid, entries):
    PROJ.mkdir(parents=True, exist_ok=True)
    with open(PROJ / f"{sid}.jsonl", "w") as f:
        for e in entries:
            e.setdefault("sessionId", sid)
            f.write(json.dumps(e) + "\n")


PR = "https://github.com/me/app/pull/{}"


def build_fixtures():
    write_session("s-decision", [user("fix the bug", 300), asst([text("Fixed it. Should I also update the docs?")], 299),
                                 {"type": "ai-title", "aiTitle": "Fix the bug"}])
    write_session("s-question", [user("plan it", 200), asst([tool("t1", "AskUserQuestion")], 199)])
    write_session("s-plan", [user("plan it", 190), asst([tool("t1", "ExitPlanMode")], 189)])
    write_session("s-closed", [user("refactor", 100), asst([text("Done, tests pass.")], 99)])
    write_session("s-midtask", [user("refactor", 100), asst([tool("t9", "Bash", {"command": "make"})], 99)])
    write_session("s-error", [user("go", 50), asst([text("API Error: overloaded")], 49, isApiErrorMessage=True)])
    write_session("s-pr-ready", [user("ship", 80), asst([tool("b1", "Bash", {"command": "gh pr create"})], 79),
                                 result("b1", 79, PR.format(1)), asst([text("Opened the draft PR.")], 78)])
    for sid, n in (("s-pr-failing", 2), ("s-pr-merged", 3), ("s-pr-changes", 4), ("s-pr-review", 6), ("s-pr-approved", 7)):
        write_session(sid, [user("ship", 80), asst([tool("c1", "mcp__github__create_pull_request")], 79),
                            result("c1", 79, json.dumps({"url": PR.format(n)})), asst([text("PR: " + PR.format(n))], 78)])
    # no create call seen, but the PR's branch is the session's branch
    write_session("s-pr-pending", [user("ship", 80), asst([text("PR: " + PR.format(5))], 79)])
    # only mentions someone else's failing PR: that mustn't make it "CI failing"
    write_session("s-pr-mentioned", [user("why is CI red on " + PR.format(2) + "?", 80),
                                     asst([text("It's a flaky test in " + PR.format(2) + ".")], 79)])
    write_session("s-start", [
        user("Work on https://linear.app/acme/issue/ENG-7/fix-login using https://www.notion.so/acme/Login-spec-0123456789abcdef0123456789abcdef", 70),
        asst([tool("l1", "mcp__linear__get_issue", {"id": "ENG-9"})], 69),
        result("l1", 69, json.dumps({"identifier": "ENG-9", "title": "Old login bug", "url": "https://linear.app/acme/issue/ENG-9"})),
        asst([text("See also https://www.notion.so/acme/Auth-notes-fedcba9876543210fedcba9876543210")], 68)])
    write_session("s-links", [user("doc", 60), asst([
        tool("w1", "Write", {"file_path": str(WORK / "plan.md")}),
    ], 59), result("w1", 59), asst([text("Published https://claude.ai/code/artifact/abc-123 and "
                                         "https://linear.app/acme/issue/ENG-42. All set.")], 58)])
    write_session("s-empty", [{"type": "summary", "summary": "nothing"}])
    write_session("s-garbage", [user("hi", 40), asst([text("Hello.")], 39)])
    with open(PROJ / "s-garbage.jsonl", "a") as f:
        f.write('[1,2]\n"str"\n{"type":"user","message":"oops"}\nnot json\n')


def usage_msg(mid, inp, cw, cr, out, m, model="claude-opus-5-5", blocks=None):
    return {"type": "assistant", "cwd": str(WORK), "timestamp": ts(m), "requestId": "r" + mid,
            "message": {"id": mid, "role": "assistant", "model": model, "content": blocks or [text("ok")],
                        "usage": {"input_tokens": inp, "cache_creation_input_tokens": cw,
                                  "cache_read_input_tokens": cr, "output_tokens": out}}}


def build_usage_fixture():
    write_session("s-usage", [
        user("count", 30),
        usage_msg("m1", 10, 1000, 5000, 200, 29, blocks=[tool("t1", "Read")]),
        usage_msg("m1", 10, 1000, 5000, 200, 29, blocks=[text("same message, second block")]),  # duplicate id
        result("t1", 29),
        usage_msg("m2", 5, 500, 6000, 300, 28),
    ])
    sub = PROJ / "s-usage" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    with open(sub / "agent-x.jsonl", "w") as f:
        f.write(json.dumps(usage_msg("s1", 1, 100, 0, 50, 28)) + "\n")
    write_session("s-old-model", [user("hi", 30), usage_msg("o1", 1, 0, 150000, 10, 29, model="claude-haiku-4-5")])


def by_id(rows):
    return {r["id"]: r for r in rows}


class ClassifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_fixtures()
        rows = cc.collect(include_all=True, days=10 ** 6)
        cc.refresh_prs([u for r in rows for u in r["prs"]], force=True)
        cls.rows = by_id(cc.collect(include_all=True, days=10 ** 6))

    def state(self, sid):
        return self.rows[sid]["state"]

    def test_needs_you_states(self):
        self.assertEqual(self.state("s-decision"), "decision")
        self.assertEqual(self.state("s-question"), "question")
        self.assertEqual(self.state("s-plan"), "plan")
        self.assertEqual(self.state("s-error"), "error")

    def test_mentioned_pr_does_not_set_state(self):
        row = self.rows["s-pr-mentioned"]
        self.assertEqual(row["state"], "closed")
        self.assertEqual([(p["number"], p["own"]) for p in row["pr_details"]], [(2, False)])
        self.assertTrue(self.rows["s-pr-pending"]["pr_details"][0]["own"])  # same branch

    def test_primary_ticket_and_page(self):
        row = self.rows["s-start"]
        lin = {r["key"]: r["primary"] for r in row["linear_list"]}
        self.assertEqual(lin, {"ENG-7": True, "ENG-9": False})
        pages = {r["title"]: r["primary"] for r in row["refs"] if r["kind"] == "notion"}
        self.assertEqual(sorted(pages.values()), [False, True])
        self.assertTrue(next(r for r in row["refs"] if "Login-spec" in r["url"])["primary"])

    def test_pr_states(self):
        self.assertEqual(self.state("s-pr-ready"), "pr_draft")
        self.assertEqual(self.state("s-pr-review"), "pr_review")
        self.assertEqual(self.state("s-pr-approved"), "pr_approved")
        self.assertEqual(self.rows["s-pr-review"]["group"], "waiting")  # waiting on reviewers, like CI
        self.assertEqual(self.rows["s-pr-ready"]["group"], "yours")
        self.assertEqual(self.rows["s-pr-pending"]["group"], "waiting")

    def test_review_requests_skip_own_prs(self):
        items = cc.fetch_review_requests()
        self.assertEqual([(r["number"], r["author"]) for r in items], [(6, "pat"), (7, "me")])
        cc.save_json(cc.REVIEWS_FILE, {"fetched": time.time(), "items": items})
        # PR 6 and 7 are both own PRs of fixture sessions; one that isn't is listed
        self.assertEqual(cc.review_requests(list(self.rows.values())), [])
        self.assertEqual([r["number"] for r in cc.review_requests([])], [6, 7])
        cc.REVIEWS_FILE.unlink()
        self.assertEqual(self.state("s-pr-failing"), "ci_failing")
        self.assertEqual(self.state("s-pr-merged"), "pr_merged")
        self.assertEqual(self.state("s-pr-changes"), "changes_requested")
        self.assertEqual(self.state("s-pr-pending"), "ci_pending")
        pr = self.rows["s-pr-ready"]["pr_details"][0]
        self.assertEqual((pr["number"], pr["draft"], pr["checks"]), (1, True, "passing"))

    def test_closed_states(self):
        self.assertEqual(self.state("s-closed"), "closed")
        self.assertEqual(self.state("s-midtask"), "closed_midtask")
        self.assertEqual(self.state("s-garbage"), "closed")

    def test_links_and_files(self):
        s = self.rows["s-links"]
        self.assertEqual(s["links"]["artifact"], ["https://claude.ai/code/artifact/abc-123"])
        self.assertEqual(s["links"]["linear"], ["https://linear.app/acme/issue/ENG-42"])
        self.assertEqual(s["files"], [str(WORK / "plan.md")])

    def test_empty_session_skipped_and_title(self):
        self.assertNotIn("s-empty", self.rows)
        self.assertEqual(self.rows["s-decision"]["display_title"], "Fix the bug")

    def test_default_list_hides_done(self):
        cc.apply_action("s-closed", "done")
        try:
            ids = {r["id"] for r in cc.collect()}
            self.assertNotIn("s-closed", ids)
            self.assertNotIn("s-pr-merged", ids)
        finally:
            cc.apply_action("s-closed", "undone")

    def test_park(self):
        cc.apply_action("s-closed", "park")
        try:
            self.assertEqual(by_id(cc.collect(True, 10 ** 6))["s-closed"]["state"], "parked")
        finally:
            cc.apply_action("s-closed", "unpark")


class UsageTest(unittest.TestCase):
    def test_tokens_counted_once_and_context(self):
        build_usage_fixture()
        rows = by_id(cc.collect(True, 10 ** 6))
        s = cc.session_json(rows["s-usage"])
        self.assertEqual(s["usage"], {"input": 15, "cache_write": 1500, "cache_read": 11000, "output": 500})
        self.assertEqual(s["sub_usage"]["output"], 50)
        self.assertEqual(s["context"], 5 + 500 + 6000)
        self.assertEqual(s["context_limit"], 1_000_000)
        self.assertEqual(s["model"], "claude-opus-5-5")
        old = cc.session_json(rows["s-old-model"])
        self.assertEqual(old["context_limit"], 200_000)

    def test_fmt_tokens(self):
        self.assertEqual([cc.fmt_tokens(n) for n in (0, 999, 92_400, 1_000_000, 15_500_000)],
                         ["0", "999", "92k", "1M", "15.5M"])


class LinksTest(unittest.TestCase):
    """Linear issues, Notion pages and artifacts: shared by you, created in the session, or mentioned."""

    @classmethod
    def setUpClass(cls):
        notion_url = "https://www.notion.so/acme/Webhook-spec-" + "a" * 32
        created_notion = "https://www.notion.so/" + "b" * 32
        entries = [
            user("Implement the webhook from " + notion_url + " and keep UTF-8 output", 30),
            asst([tool("l1", "mcp__Linear__get_issue", {"id": "ENG-42"})], 29),
            result("l1", 29, json.dumps({"identifier": "ENG-42", "title": "Stripe webhooks",
                                         "url": "https://linear.app/acme/issue/ENG-42/stripe-webhooks"})),
            asst([tool("n1", "mcp__Notion__notion-create-pages", {"pages": [{}]})], 28),
            result("n1", 28, json.dumps({"pages": [{"id": "b" * 32, "url": created_notion, "title": "Rollout plan"}]})),
            asst([tool("a1", "Artifact", {"file_path": "/tmp/x.html", "title": "Queue comparison"})], 27),
            result("a1", 27, "Published https://claude.ai/artifact/abc123XYZ (private)"),
            asst([text("Done. See ENG-42 and the plan. Also OPS-9 is unrelated.")], 26),
        ]
        for e in entries:
            e["gitBranch"] = "juraj/eng-57-email-queue"
        write_session("s-refs", entries)
        cls.s = by_id(cc.collect(True, 10 ** 6))["s-refs"]
        cls.refs = {r["url"]: r for r in cls.s["refs"]}
        cls.linear = {r["key"]: r for r in cls.s["linear_list"]}
        cls.notion_url, cls.created_notion = notion_url, created_notion

    def test_link_you_shared_gets_title_from_slug(self):
        r = self.refs[self.notion_url]
        self.assertEqual((r["kind"], r["source"], r["title"]), ("notion", "you", "Webhook spec"))

    def test_created_links_get_titles_from_tool_results(self):
        self.assertEqual((self.refs[self.created_notion]["source"], self.refs[self.created_notion]["title"]), ("created", "Rollout plan"))
        art = self.refs["https://claude.ai/artifact/abc123XYZ"]
        self.assertEqual((art["kind"], art["source"], art["title"]), ("artifact", "created", "Queue comparison"))

    def test_linear_from_tool_branch_and_mentions(self):
        self.assertEqual(self.linear["ENG-42"]["title"], "Stripe webhooks")
        self.assertEqual(self.linear["ENG-42"]["url"], "https://linear.app/acme/issue/ENG-42")
        b = self.linear["ENG-57"]  # from the branch; team ENG is known, workspace learned from ENG-42
        self.assertTrue(b["primary"])
        self.assertEqual((b["source"], b["url"]), ("branch", "https://linear.app/acme/issue/ENG-57"))
        self.assertEqual(self.s["linear_list"][0]["key"], "ENG-57")

    def test_unknown_teams_are_not_issues(self):
        self.assertNotIn("UTF-8", self.linear)
        self.assertNotIn("OPS-9", self.linear)

    def test_env_teams(self):
        os.environ["CCDECK_LINEAR_TEAMS"] = "OPS"
        try:
            s = by_id(cc.collect(True, 10 ** 6))["s-refs"]
            self.assertIn("OPS-9", {r["key"] for r in s["linear_list"]})
        finally:
            del os.environ["CCDECK_LINEAR_TEAMS"]


class HookTest(unittest.TestCase):
    def run_hook(self, payload):
        import io
        old = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        try:
            cc.cmd_hook(None)
        finally:
            sys.stdin = old

    def test_live_states_from_hooks(self):
        build_fixtures()
        sid = "s-closed"
        # Pretend this test process is the Claude process for the session.
        state_file = cc.STATE_DIR / f"{sid}.json"
        self.run_hook({"session_id": sid, "hook_event_name": "UserPromptSubmit", "cwd": str(WORK)})
        st = json.loads(state_file.read_text())
        st["pid"], st["pid_start"] = os.getpid(), cc.proc_start_time(os.getpid())
        state_file.write_text(json.dumps(st))
        self.assertEqual(by_id(cc.collect(True, 10 ** 6))[sid]["state"], "working")

        self.run_hook({"session_id": sid, "hook_event_name": "Notification",
                       "notification_type": "permission_prompt", "message": "Claude needs your permission to use Bash"})
        row = by_id(cc.collect(True, 10 ** 6))[sid]
        self.assertEqual((row["state"], row["alive"]), ("permission", True))
        self.assertIn("permission", row["hook_message"])

        self.run_hook({"session_id": sid, "hook_event_name": "Stop"})
        self.assertEqual(by_id(cc.collect(True, 10 ** 6))[sid]["state"], "idle")

        self.run_hook({"session_id": sid, "hook_event_name": "SessionEnd", "reason": "exit"})
        self.assertEqual(by_id(cc.collect(True, 10 ** 6))[sid]["state"], "closed")

    def test_bad_payloads_ignored(self):
        for p in ([1], "x", {"session_id": "../../etc"}, {}):
            self.run_hook(p)
        self.assertFalse((cc.DATA_DIR / "etc.json").exists())


class ApprovalHookTest(unittest.TestCase):
    """The PermissionRequest hook, run as Claude Code runs it: a subprocess reading JSON on stdin."""

    SID = "s-approve"

    def setUp(self):
        import subprocess
        self.subprocess = subprocess
        shutil.rmtree(cc.REQ_DIR, ignore_errors=True)
        cc.save_json(cc.DAEMON_FILE, {"pid": os.getpid(), "port": 0, "ts": time.time()})
        self.env = dict(os.environ, CCDECK_APPROVALS="1", CCDECK_APPROVAL_WAIT="15", CCDECK_AUTOSTART="0")

    def tearDown(self):
        for p in getattr(self, "procs", []):
            if p.poll() is None:
                p.kill()
        try:
            cc.DAEMON_FILE.unlink()
        except OSError:
            pass

    def hook(self, payload, env=None):
        p = self.subprocess.Popen([sys.executable, str(ROOT / "ccdeck"), "hook"], env=env or self.env,
                                  stdin=self.subprocess.PIPE, stdout=self.subprocess.PIPE, text=True)
        self.procs = getattr(self, "procs", []) + [p]
        p.stdin.write(json.dumps(payload))
        p.stdin.close()
        return p

    def ask(self, command="npm run deploy", **kw):
        return self.hook(dict({"session_id": self.SID, "hook_event_name": "PermissionRequest",
                               "cwd": str(WORK), "tool_name": "Bash",
                               "tool_input": {"command": command}}, **kw))

    def wait_request(self):
        for _ in range(100):
            reqs = cc.open_requests(self.SID)
            if reqs:
                return reqs[0]
            time.sleep(0.05)
        self.fail("no request file appeared")

    def answer(self, req, decision, h=None):
        cc.write_private(cc.REQ_DIR / f"{req['id']}.answer.json",
                         {"id": req["id"], "input_hash": h or req["input_hash"], "decision": decision})

    def finish(self, p, timeout=5):
        out = p.stdout.read()
        p.stdout.close()
        p.wait(timeout=timeout)
        return out.strip()

    def test_allow_from_dashboard(self):
        p = self.ask()
        req = self.wait_request()
        self.assertEqual((req["tool_name"], req["tool_input"]), ("Bash", {"command": "npm run deploy"}))
        self.assertEqual(oct(os.stat(cc.REQ_DIR / f"{req['id']}.json").st_mode & 0o777), "0o600")
        self.answer(req, {"behavior": "allow", "updatedInput": {"command": "rm -rf /"}})
        out = json.loads(self.finish(p))
        # Only behavior is passed on: the dashboard can't rewrite the command.
        self.assertEqual(out, {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                      "decision": {"behavior": "allow"}}})
        self.assertEqual(list(cc.REQ_DIR.iterdir()), [])

    def test_deny_with_message(self):
        p = self.ask()
        req = self.wait_request()
        self.answer(req, {"behavior": "deny", "message": "not on a Friday"})
        out = json.loads(self.finish(p))
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "deny", "message": "not on a Friday"})

    def test_answer_for_other_input_is_ignored(self):
        p = self.ask()
        req = self.wait_request()
        self.answer(req, {"behavior": "allow"}, h="0" * 64)
        self.assertEqual(self.finish(p), "")

    def test_answered_in_terminal_closes_request(self):
        p = self.ask()
        self.wait_request()
        done = self.hook({"session_id": self.SID, "hook_event_name": "PostToolUse", "tool_name": "Bash",
                          "tool_input": {"command": "npm run deploy"}, "tool_response": {}})
        self.finish(done)
        t = time.time()
        self.assertEqual(self.finish(p), "")
        self.assertLess(time.time() - t, 3)

    def test_denied_in_terminal_closes_on_next_prompt(self):
        p = self.ask()
        self.wait_request()
        self.finish(self.hook({"session_id": self.SID, "hook_event_name": "UserPromptSubmit", "prompt": "no"}))
        self.assertEqual(self.finish(p), "")

    def test_off_by_default_and_without_daemon(self):
        env = dict(self.env)
        del env["CCDECK_APPROVALS"]
        t = time.time()
        self.assertEqual(self.finish(self.hook({"session_id": self.SID, "hook_event_name": "PermissionRequest",
                                                "tool_name": "Bash", "tool_input": {"command": "ls"}}, env=env)), "")
        cc.DAEMON_FILE.unlink()
        self.assertEqual(self.finish(self.ask()), "")
        self.assertLess(time.time() - t, 3)
        self.assertEqual(cc.open_requests(self.SID), [])

    def test_valid_decision(self):
        req = {"id": "a", "input_hash": "h"}
        ok = lambda d: cc.valid_decision({"id": "a", "input_hash": "h", "decision": d}, req)
        self.assertIsNone(ok({"behavior": "ask"}))
        self.assertIsNone(ok("allow"))
        self.assertEqual(ok({"behavior": "deny", "interrupt": True}), {"behavior": "deny", "interrupt": True})
        self.assertIsNone(cc.valid_decision({"id": "b", "input_hash": "h", "decision": {"behavior": "allow"}}, req))


class InstallTest(unittest.TestCase):
    def setUp(self):
        cc.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    def args(self):
        import argparse
        return argparse.Namespace(no_hooks=False, no_service=True, port=7799)

    def test_install_keeps_other_settings_and_uninstalls(self):
        cc.SETTINGS_FILE.write_text(json.dumps({"model": "opus", "note": "žluťoučký",
                                                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}))
        cc.cmd_install(self.args())
        cc.cmd_install(self.args())  # idempotent
        s = json.loads(cc.SETTINGS_FILE.read_text())
        self.assertEqual(s["note"], "žluťoučký")
        self.assertEqual(len(s["hooks"]["Stop"]), 2)
        self.assertTrue(cc.hooks_installed())
        cc.cmd_uninstall(None)
        s = json.loads(cc.SETTINGS_FILE.read_text())
        self.assertEqual(s["hooks"], {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]})

    def test_refuses_unreadable_settings(self):
        cc.SETTINGS_FILE.write_text('{"model": "x", "bad')
        with self.assertRaises(SystemExit):
            cc.cmd_install(self.args())
        self.assertEqual(cc.SETTINGS_FILE.read_text(), '{"model": "x", "bad')
        cc.SETTINGS_FILE.unlink()


class PluginInstallTest(unittest.TestCase):
    """`ccdeck install` run from Claude Code's plugin cache hands over to a stable copy."""

    def plugin_copy(self, version):
        root = TMP / ".claude" / "plugins" / "cache" / "ccdeck" / "ccdeck" / version
        shutil.rmtree(root, ignore_errors=True)
        (root / "web").mkdir(parents=True)
        src = (ROOT / "ccdeck").read_text().replace('VERSION = "%s"' % cc.VERSION, 'VERSION = "%s"' % version)
        (root / "ccdeck").write_text(src)
        (root / "ccdeck").chmod(0o755)
        for f in (ROOT / "web").iterdir():
            shutil.copy(f, root / "web" / f.name)
        return root

    def run_ccdeck(self, script, *args, stdin=None):
        import subprocess
        env = dict(os.environ, CCDECK_AUTOSTART="0")
        env.pop("CCDECK_FROM_PLUGIN", None)
        return subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True, text=True, env=env, timeout=30)

    def tearDown(self):
        shutil.rmtree(cc.STABLE_DIR, ignore_errors=True)
        link = TMP / ".local" / "bin" / "ccdeck"
        if link.is_symlink():
            link.unlink()

    def test_install_from_plugin_uses_stable_copy(self):
        root = self.plugin_copy("9.1.0")
        r = self.run_ccdeck(root / "ccdeck", "install", "--no-hooks", "--no-service")
        self.assertEqual(r.returncode, 0, r.stderr)
        link = TMP / ".local" / "bin" / "ccdeck"
        # resolve(): on macOS the temp HOME lives under /var, a symlink to /private/var
        self.assertEqual(Path(os.readlink(link)).resolve(), (cc.STABLE_DIR / "ccdeck").resolve())
        self.assertEqual((cc.STABLE_DIR / "VERSION").read_text().strip(), "9.1.0")
        self.assertTrue((cc.STABLE_DIR / "web" / "index.html").exists())

    def test_plugin_update_refreshes_stable_copy(self):
        self.run_ccdeck(self.plugin_copy("9.1.0") / "ccdeck", "install", "--no-hooks", "--no-service")
        newer = self.plugin_copy("9.2.0")
        self.run_ccdeck(newer / "ccdeck", "hook",
                        stdin=json.dumps({"session_id": "s-up", "hook_event_name": "SessionStart"}))
        self.assertEqual((cc.STABLE_DIR / "VERSION").read_text().strip(), "9.2.0")
        self.assertIn('VERSION = "9.2.0"', (cc.STABLE_DIR / "ccdeck").read_text())

    def test_hooks_report_newer_version_to_daemon(self):
        newer = self.plugin_copy("9.3.0")
        self.run_ccdeck(newer / "ccdeck", "hook",
                        stdin=json.dumps({"session_id": "s-newer", "hook_event_name": "SessionStart"}))
        st = json.loads((cc.STATE_DIR / "s-newer.json").read_text())
        self.assertEqual(st["ccdeck"]["version"], "9.3.0")
        found = cc.newer_install()
        self.assertEqual(found[0], "9.3.0")
        self.assertEqual(Path(found[1]).resolve(), (newer / "ccdeck").resolve())
        # a state file that claims a version its script doesn't have is ignored
        st["ccdeck"]["version"] = "99.0.0"
        st["ccdeck"]["script"] = str(ROOT / "ccdeck")
        (cc.STATE_DIR / "s-newer.json").write_text(json.dumps(st))
        self.assertIsNone(cc.newer_install())
        (cc.STATE_DIR / "s-newer.json").unlink()

    def test_adopt_stable_copy_moves_service(self):
        saved = (cc.running_from_plugin, cc.service_installed, cc.systemctl)
        calls = []
        cc.running_from_plugin = lambda: True
        cc.service_installed = lambda: True
        cc.systemctl = lambda *a: calls.append(a)
        cc.UNIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        old = "/root/.claude/plugins/cache/ccdeck/ccdeck/0.4.0/ccdeck"
        cc.UNIT_FILE.write_text(f"[Service]\nExecStart=/usr/bin/python3 {old} serve --port 7799\n")
        try:
            cc.adopt_stable_copy()
            self.assertIn(f"ExecStart=/usr/bin/python3 {cc.STABLE_DIR / 'ccdeck'} serve --port 7799", cc.UNIT_FILE.read_text())
            self.assertIn(("daemon-reload",), calls)
            self.assertTrue((cc.STABLE_DIR / "ccdeck").exists())
        finally:
            cc.running_from_plugin, cc.service_installed, cc.systemctl = saved
            cc.UNIT_FILE.unlink()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_fixtures()
        cls.dash = cc.Dashboard(0)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), cls.dash.make_handler())
        cls.dash.port = cls.httpd.server_address[1]
        cls.dash.refresh()
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.dash.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def req(self, path, token=True, host=None, data=None):
        r = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None)
        if token:
            r.add_header("X-CC-Token", self.dash.token)
        if host:
            r.add_header("Host", host)
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_page_has_token(self):
        code, body = self.req("/", token=False)
        self.assertEqual(code, 200)
        self.assertIn(self.dash.token.encode(), body)

    def test_stylesheet_served(self):
        code, body = self.req("/ccdeck.css", token=False)
        self.assertEqual(code, 200)
        self.assertIn(b'data-theme="alpine-gm3a"', body)
        self.assertEqual(self.req("/../ccdeck", token=False)[0], 404)

    def test_api_requires_token_and_host(self):
        self.assertEqual(self.req("/api/sessions", token=False)[0], 403)
        self.assertEqual(self.req("/api/sessions", host="evil.example:80")[0], 403)
        code, body = self.req("/api/sessions")
        self.assertEqual(code, 200)
        snap = json.loads(body)
        self.assertIn("s-decision", {s["id"] for s in snap["sessions"]})

    def test_actions(self):
        self.assertEqual(self.req("/api/action", token=False, data={"id": "s-closed", "action": "done"})[0], 403)
        self.assertEqual(self.req("/api/action", data={"id": "nope", "action": "done"})[0], 404)
        self.assertEqual(self.req("/api/action", data={"id": "s-closed", "action": "rm -rf"})[0], 400)
        self.assertEqual(self.req("/api/action", data={"id": "s-closed", "action": "note", "text": "QA"})[0], 200)
        snap = json.loads(self.req("/api/sessions")[1])
        self.assertEqual({s["id"]: s for s in snap["sessions"]}["s-closed"]["mark"]["note"], "QA")
        self.req("/api/action", data={"id": "s-closed", "action": "note", "text": ""})


class PsProcessTest(unittest.TestCase):
    """The macOS code path (no /proc): process facts from one cached `ps` snapshot."""

    def setUp(self):
        self.saved = cc.USE_PROC
        cc.USE_PROC = False
        cc._ps_cache["t"] = 0.0

    def tearDown(self):
        cc.USE_PROC = self.saved
        cc._ps_cache["t"] = 0.0

    def test_parse_ps(self):
        rows = cc.parse_ps("  101     1 Thu Nov 12 17:31:28 2026 /Users/me/.local/bin/claude --resume x\n"
                           "  202   101 Thu Nov 12 17:31:29 2026 /bin/sh -c ccdeck hook\nnoise\n")
        self.assertEqual(rows[101], (1, "Thu Nov 12 17:31:28 2026", "/Users/me/.local/bin/claude --resume x"))
        self.assertEqual(rows[202][0], 101)
        self.assertEqual(len(rows), 2)

    @unittest.skipUnless(shutil.which("ps"), "needs ps")
    def test_liveness_from_ps(self):
        start = cc.proc_start_time(os.getpid())
        self.assertTrue(start)
        self.assertTrue(cc.pid_alive(os.getpid(), start))
        self.assertFalse(cc.pid_alive(os.getpid(), "Mon Jan  1 00:00:00 2001"))
        self.assertEqual(cc.proc_ppid(os.getpid()), os.getppid())
        self.assertTrue(cc.proc_cmdline(os.getpid()))
        self.assertIsInstance(cc.running_claude_processes(), list)

    def test_claude_detection(self):
        self.assertTrue(cc.is_claude_cmd(["/Users/me/.local/share/claude/versions/2.1.321", "--resume"]))
        self.assertTrue(cc.is_claude_cmd(["claude"]))
        self.assertFalse(cc.is_claude_cmd(["/bin/zsh"]))


class GuessLiveTest(unittest.TestCase):
    def test_n_processes_mark_n_newest_sessions_open(self):
        mk = lambda sid, ts: {"id": sid, "cwd": "/w/app", "last_ts": ts}
        sessions = {k: mk(k, ts) for k, ts in [("old", 1), ("mid", 2), ("new", 3), ("resumed", 0)]}
        procs = [(1, "/w/app", ["claude"]), (2, "/w/app", ["claude"]), (3, "/w/app", ["claude", "--resume", "resumed"])]
        live = cc.guess_live_sessions(sessions, {}, procs, "claude --resume resumed")
        self.assertEqual(live, {"new", "mid"})  # 3 processes, one of them is the resumed session
        hooks = {"new": {"pid": os.getpid(), "pid_start": cc.proc_start_time(os.getpid())}}
        self.assertEqual(cc.guess_live_sessions(sessions, hooks, procs, "claude --resume resumed"), {"mid"})


class MacDesktopTest(unittest.TestCase):
    def test_terminal_and_iterm_scripts(self):
        t = cc.mac_terminal_command("/Users/me/my \"dir\"", ["claude", "--resume", "abc"], "terminal")
        self.assertEqual(t[0], "osascript")
        self.assertIn('do script "cd \'/Users/me/my \\"dir\\"\' && claude --resume abc"', t[2])
        i = cc.mac_terminal_command("/tmp", ["claude"], "iterm")
        self.assertIn('tell application "iTerm"', i)
        self.assertTrue(any("write text" in x for x in i))

    def test_applescript_escaping(self):
        self.assertEqual(cc.applescript_str('a "b" \\ c\nd'), '"a \\"b\\" \\\\ c d"')


class TerminalTest(unittest.TestCase):
    def test_command_is_quoted(self):
        os.environ["CCDECK_TERMINAL"] = "gh --"  # any binary on PATH works for building the command
        try:
            cmd = cc.terminal_command("/tmp/it's here", ["claude", "--resume", "abc"])
        finally:
            del os.environ["CCDECK_TERMINAL"]
        self.assertEqual(cmd[:4], ["gh", "--", "bash", "-lc"])
        self.assertIn("cd '/tmp/it'\"'\"'s here' && claude --resume abc", cmd[4])


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class PreviewTest(unittest.TestCase):
    """`ccdeck preview` runs another ccdeck on the same sessions, with its own caches."""

    def test_unpack_refuses_escaping_paths(self):
        import io
        import tarfile

        def tarball(names):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for n in names:
                    info = tarfile.TarInfo(n)
                    info.size = 2
                    tar.addfile(info, io.BytesIO(b"ok"))
            return buf.getvalue()

        dest = TMP / "unpack-ok"
        cc.unpack_tarball(tarball(["repo-abc/ccdeck", "repo-abc/web/index.html"]), dest)
        self.assertEqual((dest / "web" / "index.html").read_text(), "ok")
        with self.assertRaises(RuntimeError):
            cc.unpack_tarball(tarball(["repo-abc/../../evil"]), TMP / "unpack-bad")
        self.assertFalse((TMP / "evil").exists())

    def test_fork_pr_needs_trust(self):
        saved = cc.github_json
        cc.github_json = lambda path: {"number": 9, "title": "x", "head": {"sha": "f" * 40, "repo": {"full_name": "someone/fork"}},
                                       "base": {"repo": {"full_name": "slonik923/ccdeck"}}}
        try:
            with self.assertRaises(SystemExit) as e:
                cc.resolve_preview("9", "slonik923/ccdeck", trust=False)
            self.assertIn("--trust", str(e.exception))
        finally:
            cc.github_json = saved

    def test_preview_of_local_checkout(self):
        import socket
        import subprocess
        build_fixtures()
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        env = dict(os.environ, CCDECK_AUTOSTART="0")
        r = subprocess.run([sys.executable, str(ROOT / "ccdeck"), "preview", str(ROOT), "--port", str(port), "--no-open"],
                           capture_output=True, text=True, env=env, timeout=60)
        log = lambda: (cc.PREVIEW_DIR / "serve.log").read_text() if (cc.PREVIEW_DIR / "serve.log").exists() else ""  # noqa: E731
        try:
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout + log())
            self.assertIn(f"http://localhost:{port}", r.stdout)
            cfg = cc.PREVIEW_DIR / "claude"
            for _ in range(100):  # "(still starting)" is allowed; wait for it here
                if (cfg / "ccdeck" / "token").exists():
                    try:
                        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1).close()
                        break
                    except OSError:
                        pass
                time.sleep(0.3)
            token = (cfg / "ccdeck" / "token").read_text().strip()
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/sessions", headers={"X-CC-Token": token, "Host": f"localhost:{port}"})
            snap = json.load(urllib.request.urlopen(req, timeout=5))
            self.assertTrue(snap["preview"].startswith("local "))
            self.assertIn("s-decision", {s["id"] for s in snap["sessions"]})  # your real transcripts
            self.assertNotEqual(token, cc.TOKEN_FILE.read_text().strip() if cc.TOKEN_FILE.exists() else "")
            self.assertFalse((cc.DATA_DIR / "daemon.json").exists() and
                             json.loads((cc.DATA_DIR / "daemon.json").read_text()).get("port") == port)
        finally:
            subprocess.run([sys.executable, str(ROOT / "ccdeck"), "preview", "stop"], capture_output=True, env=env, timeout=30)
        self.assertFalse((cc.PREVIEW_DIR / "preview.json").exists())

    def test_pr_preview_downloads_once(self):
        import subprocess
        tar = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar.gz", "--prefix=ccdeck-abc/", "HEAD"],
                             capture_output=True).stdout
        if not tar:
            self.skipTest("not a git checkout")
        saved = (cc.github_json, cc.download_source)
        calls = []
        cc.github_json = lambda path: {"number": 16, "title": "Group sessions", "head": {"sha": "a" * 40, "repo": {"full_name": "slonik923/ccdeck"}},
                                       "base": {"repo": {"full_name": "slonik923/ccdeck"}}}
        cc.download_source = lambda repo, sha, dest: (calls.append(sha), cc.unpack_tarball(tar, dest))
        try:
            src, label = cc.resolve_preview("16", "slonik923/cc-dashboard", trust=False)  # old name: same repo
            self.assertTrue((src / "ccdeck").is_file())
            self.assertEqual(label, "#16 Group sessions (aaaaaaa)")
            cc.resolve_preview("#16", "slonik923/ccdeck", trust=False)
            self.assertEqual(len(calls), 1)  # cached by commit
        finally:
            cc.github_json, cc.download_source = saved
