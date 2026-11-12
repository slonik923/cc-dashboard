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
        "statusCheckRollup": [{"status": "IN_PROGRESS", "conclusion": ""}]},
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
    write_session("s-pr-failing", [user("ship", 80), asst([text("PR: " + PR.format(2))], 79)])
    write_session("s-pr-merged", [user("ship", 80), asst([text("PR: " + PR.format(3))], 79)])
    write_session("s-pr-changes", [user("ship", 80), asst([text("PR: " + PR.format(4))], 79)])
    write_session("s-pr-pending", [user("ship", 80), asst([text("PR: " + PR.format(5))], 79)])
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

    def test_pr_states(self):
        self.assertEqual(self.state("s-pr-ready"), "pr_review")
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
        self.assertEqual(Path(os.readlink(link)), cc.STABLE_DIR / "ccdeck")
        self.assertEqual((cc.STABLE_DIR / "VERSION").read_text().strip(), "9.1.0")
        self.assertTrue((cc.STABLE_DIR / "web" / "index.html").exists())

    def test_plugin_update_refreshes_stable_copy(self):
        self.run_ccdeck(self.plugin_copy("9.1.0") / "ccdeck", "install", "--no-hooks", "--no-service")
        newer = self.plugin_copy("9.2.0")
        self.run_ccdeck(newer / "ccdeck", "hook",
                        stdin=json.dumps({"session_id": "s-up", "hook_event_name": "SessionStart"}))
        self.assertEqual((cc.STABLE_DIR / "VERSION").read_text().strip(), "9.2.0")
        self.assertIn('VERSION = "9.2.0"', (cc.STABLE_DIR / "ccdeck").read_text())


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
