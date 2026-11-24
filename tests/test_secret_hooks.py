"""Tests for the secret-check hooks in .githooks/, run through real commits in a scratch repository."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Assembled at run time, so that this file does not trip the check it tests.
BODY = "Zx8Qw3Lr7Tn2Vb9Kd4Mf6Hs1Jp5Gc0Yt"
OAUTH = "sk-ant-" + "oat01-" + BODY
HUB = "HUB_" + "TOKEN=" + BODY
# The copy that `make setup` installed, as the hooks resolve it.
GITLEAKS = subprocess.run(["sh", "-c", '. .githooks/gitleaks.sh; echo "$GITLEAKS"'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
HAVE_GITLEAKS = os.access(GITLEAKS, os.X_OK)


class SecretHooksTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        # Git exports its location into a hook's environment; drop it so that these commands act on
        # the scratch repository even when the suite runs from a hook.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GITLEAKS"))}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GITLEAKS=GITLEAKS)
        shutil.copytree(ROOT / ".githooks", self.dir / ".githooks")
        shutil.copy(ROOT / ".gitleaks.toml", self.dir)
        (self.dir / "scripts").mkdir()
        for name in ("check_secrets.sh", "setup.sh"):
            shutil.copy(ROOT / "scripts" / name, self.dir / "scripts")
        shutil.copy(ROOT / "Makefile", self.dir)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "t")
        self.git("config", "user.email", "t@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.git("config", "core.hooksPath", ".githooks")

    def run_cmd(self, *cmd, cwd=None, **env):
        return subprocess.run(cmd, cwd=cwd or self.dir, env={**self.env, **env},
                              capture_output=True, text=True)

    def git(self, *args, **kw):
        r = self.run_cmd("git", *args, **kw)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def commit(self, content, message="change", cwd=None, **env):
        (Path(cwd or self.dir) / "f.txt").write_text(content + "\n")
        self.git("add", "f.txt", cwd=cwd)
        return self.run_cmd("git", "commit", "-qm", message, cwd=cwd, **env)

    def assert_blocked(self, r, where):
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("commit blocked: gitleaks reported a problem in " + where, r.stderr)
        self.assertNotIn(BODY, r.stdout + r.stderr)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks is not installed")
    def test_staged_secrets_are_blocked_and_redacted(self):
        for secret in (OAUTH, HUB):
            with self.subTest(secret[:10]):
                self.assert_blocked(self.commit(secret), "the staged change")

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks is not installed")
    def test_references_to_the_token_pass(self):
        text = 'export HUB_TOKEN="$SOME_LONG_VARIABLE_NAME"\nHUB_TOKEN=<token>\n' \
               'token=os.environ.get("HUB_TOKEN")\nGITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}'
        r = self.commit(text)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks is not installed")
    def test_a_secret_in_the_message_is_blocked(self):
        self.assert_blocked(self.commit("ok", message="use " + OAUTH), "the commit message")

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks is not installed")
    def test_a_merge_that_brings_a_secret_is_blocked(self):
        self.git("checkout", "-qb", "side")
        (self.dir / "f.txt").write_text(OAUTH + "\n")
        self.git("add", "f.txt")
        self.git("commit", "-qnm", "side")  # -n: the bypassed hook the merge must make up for
        self.git("checkout", "-q", "main")
        r = self.run_cmd("git", "merge", "--no-ff", "-m", "merge", "side")
        self.assert_blocked(r, "the staged change")

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks is not installed")
    def test_the_hooks_run_in_a_linked_worktree(self):
        tree = self.dir / "tree"
        self.git("worktree", "add", "-q", str(tree))
        self.assert_blocked(self.commit(OAUTH, cwd=tree), "the staged change")

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks is not installed")
    def test_the_history_scan_finds_a_secret_that_a_later_commit_removed(self):
        self.assertEqual(self.run_cmd("scripts/check_secrets.sh").returncode, 0)
        (self.dir / "f.txt").write_text(OAUTH + "\n")
        self.git("add", "f.txt")
        self.git("commit", "-qnm", "leak")
        self.assertEqual(self.commit("clean").returncode, 0)
        r = self.run_cmd("scripts/check_secrets.sh")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn(BODY, r.stdout + r.stderr)

    @unittest.skipUnless(HAVE_GITLEAKS, "gitleaks is not installed")
    def test_the_history_scan_finds_a_secret_added_by_a_merge_commit_itself(self):
        self.git("checkout", "-qb", "side")
        self.assertEqual(self.commit("side").returncode, 0)
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", "--no-commit", "side")
        (self.dir / "extra.txt").write_text(OAUTH + "\n")
        self.git("add", "extra.txt")
        self.git("commit", "-qnm", "merge")
        self.assertNotEqual(self.run_cmd("scripts/check_secrets.sh").returncode, 0)

    def test_without_gitleaks_the_commit_and_the_scan_are_blocked(self):
        for r in (self.commit("ok", GITLEAKS="/no/gitleaks"),
                  self.run_cmd("scripts/check_secrets.sh", GITLEAKS="/no/gitleaks")):
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("run: make setup", r.stderr)

    def hooks_path(self):
        return self.run_cmd("git", "config", "core.hooksPath").stdout.strip()

    @unittest.skipUnless(shutil.which("make"), "make is not installed")
    def test_make_setup_enables_the_hooks_and_can_run_again(self):
        self.git("config", "--unset", "core.hooksPath")
        for _ in range(2):
            r = self.run_cmd("make", "setup", GITLEAKS="/bin/echo")  # stands in for an installed copy
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.hooks_path(), ".githooks")

    def test_setup_keeps_another_hooks_folder(self):
        self.git("config", "core.hooksPath", "other")
        r = self.run_cmd("scripts/setup.sh", GITLEAKS="/bin/echo")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.hooks_path(), "other")

    def serve_archive(self):
        """Put a fake release where setup.sh downloads from; return (base URL, its checksum)."""
        src = self.dir / "release"
        src.mkdir()
        (src / "gitleaks").write_text("#!/bin/sh\n")
        (src / "gitleaks").chmod(0o755)
        for os_name in ("darwin", "linux"):
            for arch in ("x64", "arm64"):
                name = src / f"gitleaks_8.30.1_{os_name}_{arch}.tar.gz"
                if not (src / "a.tar.gz").exists():
                    subprocess.run(["tar", "-czf", src / "a.tar.gz", "-C", src, "gitleaks"], check=True)
                shutil.copy(src / "a.tar.gz", name)
        return src.as_uri(), hashlib.sha256((src / "a.tar.gz").read_bytes()).hexdigest()

    def test_setup_refuses_a_download_that_does_not_match_its_checksum(self):
        base, _ = self.serve_archive()
        target = self.dir / "tools" / "gitleaks"
        self.git("config", "--unset", "core.hooksPath")
        r = self.run_cmd("scripts/setup.sh", GITLEAKS=str(target), GITLEAKS_BASE_URL=base)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not match its checksum", r.stderr)
        self.assertEqual(list(target.parent.iterdir()), [])
        self.assertEqual(self.hooks_path(), "")

    def test_setup_installs_gitleaks_once_for_every_worktree(self):
        base, digest = self.serve_archive()
        script = self.dir / "scripts" / "setup.sh"
        script.write_text(re.sub(r"echo [0-9a-f]{64}", "echo " + digest, script.read_text()))
        self.git("config", "--unset", "core.hooksPath")
        del self.env["GITLEAKS"]
        r = self.run_cmd("scripts/setup.sh", GITLEAKS_BASE_URL=base)
        self.assertEqual(r.returncode, 0, r.stderr)
        tree = self.dir / "tree"
        self.git("worktree", "add", "-q", str(tree))
        self.assertEqual(self.run_cmd("scripts/setup.sh", "--check", cwd=tree).returncode, 0)

    def test_the_session_hooks_set_up_and_block_edits_until_then(self):
        hooks = json.loads((ROOT / ".claude" / "settings.json").read_text())["hooks"]
        start = hooks["SessionStart"][0]["hooks"][0]["command"]
        guard = hooks["PreToolUse"][0]["hooks"][0]["command"]
        env = {"CLAUDE_PROJECT_DIR": str(self.dir), "GITLEAKS": "/bin/echo"}
        self.git("config", "--unset", "core.hooksPath")
        r = self.run_cmd("sh", "-c", guard, **env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("make setup", r.stderr)
        r = self.run_cmd("sh", "-c", start, **env)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.run_cmd("sh", "-c", guard, **env).returncode, 0)
        self.git("config", "core.hooksPath", "other")  # a setup that fails says why
        self.assertIn("core.hooksPath", self.run_cmd("sh", "-c", start, **env).stdout)


if __name__ == "__main__":
    unittest.main()
