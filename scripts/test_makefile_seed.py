"""Regression tests: the Docker seed targets must take USER only from the command line."""

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED_TARGETS = ["seed-users", "seed-kus", "seed-all"]


def run_make(target, *args, env_user=None):
    env = dict(os.environ)
    if env_user is not None:
        env["USER"] = env_user
    return subprocess.run(
        ["make", "-n", target, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


class SeedTargetsRejectEnvironmentUser(unittest.TestCase):
    def test_env_user_is_rejected(self):
        # USER is exported by POSIX shells; each target must still refuse it.
        for target in SEED_TARGETS:
            with self.subTest(target=target):
                result = run_make(target, "PASS=secret", env_user="osuser")
                self.assertNotEqual(
                    result.returncode,
                    0,
                    f"{target} accepted env USER; stdout={result.stdout!r}",
                )


class SeedTargetsAcceptCommandLineUser(unittest.TestCase):
    def test_command_line_user_is_accepted(self):
        # A command-line USER must still work, and must win over the env value.
        for target in SEED_TARGETS:
            with self.subTest(target=target):
                result = run_make(target, "USER=demo", "PASS=secret", env_user="osuser")
                self.assertEqual(
                    result.returncode,
                    0,
                    f"{target} rejected command-line USER; stderr={result.stderr!r}",
                )
                self.assertIn("demo", result.stdout)
                self.assertNotIn("osuser", result.stdout)


class SeedTargetsRejectEmptyCommandLineUser(unittest.TestCase):
    def test_empty_or_whitespace_command_line_user_is_rejected(self):
        for target in SEED_TARGETS:
            for user_value in ("", "   "):
                with self.subTest(target=target, user_value=repr(user_value)):
                    result = run_make(
                        target,
                        f"USER={user_value}",
                        "PASS=secret",
                        env_user="osuser",
                    )
                    self.assertNotEqual(
                        result.returncode,
                        0,
                        f"{target} accepted command-line USER={user_value!r}; "
                        f"stdout={result.stdout!r}",
                    )
                    self.assertIn("USER is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
