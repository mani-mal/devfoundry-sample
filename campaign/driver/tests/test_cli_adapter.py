"""Offline unit tests for the dry-run DevFoundry CLI adapter."""

from __future__ import annotations

import unittest

from campaign.driver import cli_adapter


class TestBuildSubmitArgv(unittest.TestCase):
    def test_exact_array_equality(self):
        argv = cli_adapter.DevFoundryAdapter.build_submit_argv(
            title="Add journal index rebuild",
            project="df-project",
            repo="df-repo",
            base="main",
            request_path="/tmp/request.txt",
        )
        self.assertEqual(
            argv,
            [
                "devfoundry",
                "submit",
                "Add journal index rebuild",
                "--project",
                "df-project",
                "--repo",
                "df-repo",
                "--base",
                "main",
                "--mode",
                "implement",
                "--autonomy",
                "workspace",
                "--environment",
                "polyglot",
                "--request-file",
                "/tmp/request.txt",
            ],
        )

    def test_preview_true_appends_preview(self):
        argv = cli_adapter.DevFoundryAdapter.build_submit_argv(
            title="T",
            project="p",
            repo="r",
            base="main",
            request_path="/tmp/request.txt",
            preview=True,
        )
        self.assertEqual(argv[-1], "--preview")
        argv_plain = cli_adapter.DevFoundryAdapter.build_submit_argv(
            title="T",
            project="p",
            repo="r",
            base="main",
            request_path="/tmp/request.txt",
        )
        self.assertNotIn("--preview", argv_plain)

    def test_empty_arg_raises_value_error(self):
        with self.assertRaises(ValueError):
            cli_adapter.DevFoundryAdapter.build_submit_argv(
                title="",
                project="p",
                repo="r",
                base="main",
                request_path="/tmp/request.txt",
            )
        with self.assertRaises(ValueError):
            cli_adapter.DevFoundryAdapter.build_submit_argv(
                title="T",
                project="",
                repo="r",
                base="main",
                request_path="/tmp/request.txt",
            )

    def test_newline_in_title_raises_value_error(self):
        with self.assertRaises(ValueError):
            cli_adapter.DevFoundryAdapter.build_submit_argv(
                title="bad\ntitle",
                project="p",
                repo="r",
                base="main",
                request_path="/tmp/request.txt",
            )

    def test_whitespace_only_arg_raises_value_error(self):
        with self.assertRaises(ValueError):
            cli_adapter.DevFoundryAdapter.build_submit_argv(
                title="T",
                project="p",
                repo="r",
                base="   ",
                request_path="/tmp/request.txt",
            )


class TestBuildWatchArgv(unittest.TestCase):
    def test_valid_tsk_prefix_passes(self):
        argv = cli_adapter.DevFoundryAdapter.build_watch_argv("tsk-abc12345")
        self.assertEqual(argv, ["devfoundry", "watch", "tsk-abc12345"])
        argv_full = cli_adapter.DevFoundryAdapter.build_watch_argv("tsk-" + "a" * 64)
        self.assertEqual(argv_full, ["devfoundry", "watch", "tsk-" + "a" * 64])

    def test_invalid_task_ids_raise_value_error(self):
        for bad in ("hello", "tsk-xyz", "tsk-", "tsk-abc123", "tsk-ABC12345", "task-abc12345"):
            with self.assertRaises(ValueError):
                cli_adapter.DevFoundryAdapter.build_watch_argv(bad)

    def test_too_short_hex_prefix_raises(self):
        with self.assertRaises(ValueError):
            cli_adapter.DevFoundryAdapter.build_watch_argv("tsk-abc123")


class TestDryRunMode(unittest.TestCase):
    def test_dry_run_result_label_is_fixture(self):
        adapter = cli_adapter.DevFoundryAdapter("http://example.invalid", adapter_mode="dry_run")
        result = adapter.submit(
            title="T",
            project="p",
            repo="r",
            base="main",
            request_path="/tmp/request.txt",
        )
        self.assertEqual(result.label, "fixture")
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.argv[0], "devfoundry")

    def test_dry_run_stdout_contains_fixture_and_no_submitted_marker(self):
        adapter = cli_adapter.DevFoundryAdapter("http://example.invalid", adapter_mode="dry_run")
        result = adapter.submit(
            title="T",
            project="p",
            repo="r",
            base="main",
            request_path="/tmp/request.txt",
        )
        self.assertIn("fixture", result.stdout)
        self.assertIn("fixture: dry-run submit (no live task claimed)", result.stdout)
        self.assertNotIn("Submitted tsk-", result.stdout)
        self.assertIn("mode: implement", result.stdout)
        self.assertIn("autonomy: workspace", result.stdout)
        self.assertIn("isolation:", result.stdout)

    def test_policy_preview_block_labelled_fixture(self):
        adapter = cli_adapter.DevFoundryAdapter("http://example.invalid", adapter_mode="dry_run")
        block = adapter.build_policy_preview_block(
            mode="implement",
            autonomy="workspace",
            isolation="pod-per-task",
            allowed=["workspace/ edits"],
            ask=["nothing"],
            denied=["network egress"],
            pack="opsledger-baseline",
            pack_version="1",
            role="implement",
            profile="polyglot",
        )
        self.assertIn("fixture", block)
        self.assertIn("mode: implement", block)
        self.assertIn("autonomy: workspace", block)
        self.assertIn("isolation: pod-per-task", block)
        self.assertIn("pack: opsledger-baseline", block)
        self.assertIn("pack_version: 1", block)
        self.assertIn("role: implement", block)
        self.assertIn("profile: polyglot", block)


class TestParseSubmittedTaskId(unittest.TestCase):
    def test_parses_submitted_marker(self):
        stdout = "Submitted tsk-abc12345 · base main\n"
        self.assertEqual(cli_adapter.parse_submitted_task_id(stdout), "tsk-abc12345")

    def test_parses_full_hex_id(self):
        stdout = "Submitted tsk-" + "0123abcd" * 8 + " · base main\n"
        task_id = "tsk-" + "0123abcd" * 8
        self.assertEqual(cli_adapter.parse_submitted_task_id(stdout), task_id)

    def test_returns_none_without_marker(self):
        self.assertIsNone(cli_adapter.parse_submitted_task_id("nothing here"))
        self.assertIsNone(cli_adapter.parse_submitted_task_id(""))

    def test_does_not_parse_human_title(self):
        stdout = "Fix tsk-abc12345 onboarding issue\nDone.\n"
        self.assertIsNone(cli_adapter.parse_submitted_task_id(stdout))

    def test_ignores_tsk_mention_in_body_without_submitted_marker(self):
        stdout = "Watch tsk-abc12345 · base main\n"
        self.assertIsNone(cli_adapter.parse_submitted_task_id(stdout))


class TestLiveMode(unittest.TestCase):
    def test_live_without_runner_raises_runtime_error(self):
        adapter = cli_adapter.DevFoundryAdapter("http://example.invalid", adapter_mode="live")
        with self.assertRaises(RuntimeError) as caught:
            adapter.submit(
                title="T",
                project="p",
                repo="r",
                base="main",
                request_path="/tmp/request.txt",
            )
        self.assertIn("operator authorization", str(caught.exception))
        self.assertIn("adapter runner not configured", str(caught.exception))

    def test_live_with_injected_runner_calls_runner(self):
        seen: list[list[str]] = []

        def fake_runner(argv: list[str]):
            seen.append(argv)
            return "ran"

        adapter = cli_adapter.DevFoundryAdapter("http://example.invalid", adapter_mode="live", runner=fake_runner)
        result = adapter.submit(
            title="T",
            project="p",
            repo="r",
            base="main",
            request_path="/tmp/request.txt",
        )
        self.assertEqual(result, "ran")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], "devfoundry")

    def test_invalid_adapter_mode_raises(self):
        with self.assertRaises(ValueError):
            cli_adapter.DevFoundryAdapter("http://example.invalid", adapter_mode="sudo")


if __name__ == "__main__":
    unittest.main()
