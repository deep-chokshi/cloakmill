"""Behavioral tests for the review collector and publisher; no model or network is used."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from claude_review import (
    ReviewError,
    collect,
    diagnostics,
    extract_report,
    extract_result,
    package_results,
    publish_review,
)

REPO = "example-org/example-repo"
HEAD = "b" * 40
BASE = "a" * 40
CONTEXT = {
    "repository": REPO,
    "number": 2,
    "head_sha": HEAD,
    "base_sha": BASE,
    "run_id": 123,
    "run_attempt": 1,
    "server_url": "https://github.com",
}
FILE = {
    "filename": "src/example.py",
    "patch": "@@ -1,2 +1,3 @@\n context\n+new_line\n context",
}
FINDING = {
    "path": FILE["filename"],
    "line": 2,
    "severity": "high",
    "confidence": 0.95,
    "title": "Concrete regression",
    "explanation": "This input produces an incorrect result.",
    "evidence": "The added expression changes the value.",
    "recommendation": "Correct it.",
}
STATS = {
    "turns": 12,
    "tool_calls": 30,
    "subagent_tool_calls": 24,
    "permission_denials": 0,
    "cost_usd": 1.2345,
    "duration_ms": 90000,
}


def result(kind, findings=None):
    return {
        "review_type": kind,
        "reviewed_head": HEAD,
        "status": "completed",
        "summary": "Reviewed the change.",
        "findings": findings or [],
        "limitations": ["Source inspection only; no project tests were executed."],
    }


def bundle():
    return {
        "repository": REPO,
        "number": 2,
        "head_sha": HEAD,
        "base_sha": BASE,
        "results": {
            kind: {
                "outcome": "success",
                "data": result(kind),
                "diagnostics": {"review": dict(STATS), "structure": dict(STATS, turns=3)},
            }
            for kind in ("code", "security")
        },
    }


def envelope(**overrides):
    base = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 4,
        "duration_ms": 1000,
        "total_cost_usd": 0.5,
        "permission_denials": [],
        "result": "1 finding:\n1. `src/example.py:2`: wrong value",
    }
    return dict(base, **overrides)


def session(*blocks, parent=None):
    content = [{"type": "tool_use", "id": f"call-{i}", **block} for i, block in enumerate(blocks)]
    message = {"type": "assistant", "message": {"content": content}}
    if parent:
        message["parent_tool_use_id"] = parent
    return message


class FakeGitHub:
    def __init__(self):
        self.pr = {
            "state": "open",
            "draft": False,
            "changed_files": 1,
            "head": {"sha": HEAD, "repo": {"full_name": REPO}},
            "base": {"sha": BASE, "repo": {"full_name": REPO}},
        }
        self.files = [FILE]
        self.reviews = []
        self.posts = []
        self.fail_post = False

    def get(self, path):
        if "/reviews/" in path:
            return self.reviews[-1]
        return copy.deepcopy(self.pr)

    def paginate(self, path):
        return self.files if "/files" in path else self.reviews

    def post(self, path, payload):
        if self.fail_post:
            raise ReviewError("GitHub publication failed")
        self.posts.append((path, payload))
        review = {
            "id": 10,
            "body": payload["body"],
            "commit_id": payload["commit_id"],
            "state": "COMMENTED",
            "user": {"login": "github-actions[bot]"},
            "html_url": f"https://github.com/{REPO}/pull/2#pullrequestreview-10",
        }
        self.reviews.append(review)
        return review


class ReviewStageTests(unittest.TestCase):
    def test_review_stage_captures_the_commands_report_from_a_real_run(self):
        entry = extract_report([session({"name": "Read", "input": {}}), envelope()], "success")
        self.assertEqual(entry["outcome"], "success")
        self.assertIn("src/example.py:2", entry["report"])
        self.assertEqual(entry["diagnostics"]["turns"], 4)

    def test_zero_turn_success_such_as_an_authentication_failure_is_not_a_review(self):
        auth = envelope(num_turns=0, result="Failed to authenticate: OAuth session expired")
        entry = extract_report([auth], "success")
        self.assertEqual(entry["outcome"], "failure")
        self.assertIsNone(entry["report"])
        self.assertIn("no completed turns", entry["reason"])

    def test_errors_empty_replies_and_failed_steps_never_yield_a_report(self):
        for messages, outcome in (
            ([envelope(subtype="error_max_budget_usd")], "success"),
            ([envelope(is_error=True)], "success"),
            ([envelope(result="   ")], "success"),
            ([envelope()], "failure"),
            ([{"type": "assistant", "message": {"content": "prose only"}}], "success"),
            (None, "success"),
        ):
            with self.subTest(messages=messages, outcome=outcome):
                self.assertEqual(extract_report(messages, outcome)["outcome"], "failure")

    def test_structuring_stage_requires_the_sdk_structured_output(self):
        good = envelope(structured_output=result("code"))
        self.assertEqual(extract_result([good], "success")["data"], result("code"))
        for override, outcome in (
            ({"subtype": "error_max_turns"}, "success"),
            ({"is_error": True}, "success"),
            ({"permission_denials": [{"tool_name": "Bash"}]}, "success"),
            ({"structured_output": "not an object"}, "success"),
            ({}, "skipped"),
        ):
            with self.subTest(override=override, outcome=outcome):
                entry = extract_result([dict(good, **override)], outcome)
                self.assertEqual(entry["outcome"], "failure")
                self.assertIsNone(entry["data"])

    def test_a_prose_claim_without_structured_output_is_not_a_result(self):
        messages = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}},
            envelope(),
        ]
        self.assertEqual(extract_result(messages, "success")["outcome"], "failure")

    def test_empty_or_malformed_execution_data_is_incomplete(self):
        for value in ([], {}, None, ["invalid"]):
            self.assertEqual(extract_result(value, "success")["outcome"], "failure")
            self.assertEqual(extract_report(value, "success")["outcome"], "failure")

    def test_diagnostics_keep_counts_and_targets_but_never_tool_output(self):
        messages = [
            {"type": "system", "subtype": "init", "model": "claude-example"},
            session(
                {"name": "Bash", "input": {"command": "git diff origin/HEAD..."}},
                {"name": "Agent", "input": {"description": "find bugs", "prompt": "long " * 100}},
            ),
            session({"name": "Read", "input": {"file_path": "src/example.py"}}, parent="call-1"),
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "call-0", "content": "SECRET-OUTPUT"}
                    ]
                },
            },
            envelope(
                permission_denials=[{"tool_name": "Bash", "tool_input": {"command": "rm -rf"}}]
            ),
        ]
        summary = diagnostics(messages)
        self.assertEqual(summary["model"], "claude-example")
        self.assertEqual(summary["tool_calls"], 3)
        self.assertEqual(summary["subagent_tool_calls"], 1)
        self.assertEqual(summary["tools"], {"Bash": 1, "Agent": 1, "Read": 1})
        self.assertEqual(summary["permission_denials"], 1)
        self.assertEqual(summary["denials"], [["Bash", "rm -rf"]])
        self.assertIn(["sub", "Read", "src/example.py"], summary["trace"])
        self.assertIn(["main", "Agent", "find bugs"], summary["trace"])
        serialized = json.dumps(summary)
        self.assertNotIn("SECRET-OUTPUT", serialized)
        self.assertNotIn("long long", serialized)

    def test_collect_writes_report_diagnostics_and_bundle_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            results = temp / "results"
            control = temp / "control"
            execution = temp / "claude-execution-output.json"
            summary = temp / "summary.md"
            output = temp / "output.txt"
            env = {
                "RUNNER_TEMP": str(temp),
                "CLOAKMILL_EXECUTION_FILE": str(execution),
                "CLOAKMILL_ACTION_OUTCOME": "success",
                "GITHUB_STEP_SUMMARY": str(summary),
                "GITHUB_OUTPUT": str(output),
            }
            execution.write_text(json.dumps([session({"name": "Read", "input": {}}), envelope()]))
            with mock.patch.dict(os.environ, env):
                collect("code", "review", results / "code-review.json", control / "code-report.md")
            self.assertIn("src/example.py:2", (control / "code-report.md").read_text())
            self.assertIn("outcome=success", output.read_text())
            self.assertIn("**code review**: success", summary.read_text())
            review = json.loads((results / "code-review.json").read_text())
            self.assertEqual(review["stats"]["turns"], 4)
            self.assertNotIn("report", review)
            stage = json.loads((results / "diagnostics" / "code-review.json").read_text())
            self.assertIn("src/example.py:2", stage["report"])

            execution.write_text(json.dumps([envelope(structured_output=result("code"))]))
            with mock.patch.dict(os.environ, env):
                collect("code", "structure", results / "code.json", None)
            entry = json.loads((results / "code.json").read_text())
            self.assertEqual(entry["outcome"], "success")
            self.assertEqual(entry["data"], result("code"))
            self.assertEqual(entry["diagnostics"]["review"]["turns"], 4)
            self.assertEqual(entry["diagnostics"]["structure"]["turns"], 4)

            execution.unlink()
            with mock.patch.dict(os.environ, dict(env, CLOAKMILL_ACTION_OUTCOME="skipped")):
                collect("security", "structure", results / "security.json", None)
            entry = json.loads((results / "security.json").read_text())
            self.assertEqual(entry["outcome"], "failure")
            self.assertEqual(entry["diagnostics"], {"review": {}, "structure": {}})
            self.assertIn("**security structure**: failure", summary.read_text())

    def test_execution_file_is_only_read_from_the_expected_location(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            elsewhere = temp / "elsewhere.json"
            elsewhere.write_text(json.dumps([envelope()]))
            env = {
                "RUNNER_TEMP": str(temp),
                "CLOAKMILL_EXECUTION_FILE": str(elsewhere),
                "CLOAKMILL_ACTION_OUTCOME": "success",
            }
            with mock.patch.dict(os.environ, env):
                collect("code", "review", temp / "code-review.json", temp / "code-report.md")
            self.assertEqual(
                json.loads((temp / "code-review.json").read_text())["outcome"], "failure"
            )
            self.assertFalse((temp / "code-report.md").exists())


class ReviewPublisherTests(unittest.TestCase):
    def test_missing_security_file_packages_as_incomplete_for_visible_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "code.json").write_text(
                json.dumps({"outcome": "success", "data": result("code"), "diagnostics": {}})
            )
            data = package_results(folder, CONTEXT)
            self.assertEqual(data["results"]["security"]["outcome"], "failure")
            api = FakeGitHub()
            _, passed = publish_review(api, data, CONTEXT)
            self.assertFalse(passed)
            self.assertIn("Security review: incomplete", api.posts[0][1]["body"])

    def test_both_completed_passes_publish_an_explicit_clean_review(self):
        api = FakeGitHub()
        url, passed = publish_review(api, bundle(), CONTEXT)
        self.assertTrue(passed)
        payload = api.posts[0][1]
        self.assertEqual(payload["event"], "COMMENT")
        self.assertEqual(payload["commit_id"], HEAD)
        self.assertIn("Review-Result: no-actionable-findings", payload["body"])
        self.assertIn("Code review: completed", payload["body"])
        self.assertIn("Security review: completed", payload["body"])
        self.assertIn(HEAD, payload["body"])
        self.assertIn("actions/runs/123", payload["body"])
        self.assertIn("pullrequestreview-10", url)

    def test_stage_statistics_are_published_as_numbers_only(self):
        data = bundle()
        data["results"]["code"]["diagnostics"]["review"].update(
            {"turns": "<script>", "cost_usd": float("nan"), "tool_calls": "@all"}
        )
        api = FakeGitHub()
        publish_review(api, data, CONTEXT)
        body = api.posts[0][1]["body"]
        self.assertIn(
            "Review stage: n/a turns, n/a tool calls (24 in subagents), 0 permission", body
        )
        self.assertIn(
            "Structuring stage: 3 turns, 30 tool calls (24 in subagents), 0 permission", body
        )
        self.assertIn("$1.23, 90 s", body)
        self.assertNotIn("<script>", body)
        self.assertNotIn("@all", body)

    def test_missing_statistics_do_not_block_publication(self):
        data = bundle()
        data["results"]["code"].pop("diagnostics")
        data["results"]["security"]["diagnostics"] = "not a mapping"
        api = FakeGitHub()
        _, passed = publish_review(api, data, CONTEXT)
        self.assertTrue(passed)
        self.assertNotIn("stage:", api.posts[0][1]["body"])

    def test_verified_findings_are_inline_and_fail_the_gate(self):
        data = bundle()
        data["results"]["security"]["data"]["findings"] = [FINDING]
        api = FakeGitHub()
        _, passed = publish_review(api, data, CONTEXT)
        self.assertFalse(passed)
        payload = api.posts[0][1]
        self.assertIn("Review-Result: findings", payload["body"])
        self.assertEqual(payload["comments"][0]["path"], FILE["filename"])
        self.assertEqual(payload["comments"][0]["line"], 2)
        self.assertEqual(payload["comments"][0]["side"], "RIGHT")

    def test_missing_or_failed_pass_is_never_clean(self):
        for value in (None, "", {"outcome": "failure", "data": result("security")}):
            with self.subTest(value=value):
                data = bundle()
                data["results"]["security"] = value
                api = FakeGitHub()
                _, passed = publish_review(api, data, CONTEXT)
                self.assertFalse(passed)
                self.assertIn("Review-Result: incomplete", api.posts[0][1]["body"])
                self.assertNotIn("Review-Result: no-actionable-findings", api.posts[0][1]["body"])

    def test_schema_mismatches_produce_an_incomplete_result(self):
        for field, value in (
            ("status", "unknown"),
            ("reviewed_head", "c" * 40),
            ("review_type", "security"),
            ("findings", "none"),
            ("summary", ""),
            ("limitations", []),
        ):
            with self.subTest(field=field):
                data = bundle()
                data["results"]["code"]["data"][field] = value
                api = FakeGitHub()
                _, passed = publish_review(api, data, CONTEXT)
                self.assertFalse(passed)
                self.assertIn("Review-Result: incomplete", api.posts[0][1]["body"])

    def test_explicit_incomplete_pass_does_not_claim_no_findings(self):
        data = bundle()
        data["results"]["code"]["data"]["status"] = "incomplete"
        api = FakeGitHub()
        _, passed = publish_review(api, data, CONTEXT)
        self.assertFalse(passed)
        self.assertIn("Code review: incomplete", api.posts[0][1]["body"])

    def test_stale_head_or_base_prevents_publication(self):
        for revision in ("head", "base"):
            with self.subTest(revision=revision):
                api = FakeGitHub()
                api.pr[revision]["sha"] = "c" * 40
                with self.assertRaises(ReviewError):
                    publish_review(api, bundle(), CONTEXT)
                self.assertEqual(api.posts, [])

    def test_closed_draft_and_fork_targets_prevent_publication(self):
        for mutation in (
            lambda p: p.update(state="closed"),
            lambda p: p.update(draft=True),
            lambda p: p["head"].update(repo=None),
            lambda p: p["head"]["repo"].update(full_name="someone/fork"),
        ):
            api = FakeGitHub()
            mutation(api.pr)
            with self.assertRaises(ReviewError):
                publish_review(api, bundle(), CONTEXT)
            self.assertEqual(api.posts, [])

    def test_artifact_target_cannot_redirect_publication(self):
        for key, value in (
            ("repository", "other/repo"),
            ("number", 7),
            ("head_sha", "c" * 40),
            ("base_sha", "c" * 40),
        ):
            data = bundle()
            data[key] = value
            api = FakeGitHub()
            with self.assertRaises(ReviewError):
                publish_review(api, data, CONTEXT)
            self.assertEqual(api.posts, [])

    def test_invalid_findings_cannot_be_published_as_clean(self):
        for key, value in (
            ("path", "../secrets"),
            ("path", "unmodified.py"),
            ("line", 999),
            ("line", True),
            ("confidence", 0.4),
            ("confidence", float("nan")),
            ("severity", "guess"),
        ):
            with self.subTest(key=key, value=value):
                data = bundle()
                finding = dict(FINDING, **{key: value})
                data["results"]["code"]["data"]["findings"] = [finding]
                api = FakeGitHub()
                _, passed = publish_review(api, data, CONTEXT)
                self.assertFalse(passed)
                self.assertIn("Review-Result: incomplete", api.posts[0][1]["body"])
                self.assertEqual(api.posts[0][1].get("comments", []), [])

    def test_low_confidence_security_and_test_only_findings_are_incomplete(self):
        data = bundle()
        data["results"]["security"]["data"]["findings"] = [dict(FINDING, severity="low")]
        api = FakeGitHub()
        _, passed = publish_review(api, data, CONTEXT)
        self.assertFalse(passed)
        self.assertIn("Review-Result: incomplete", api.posts[0][1]["body"])

    def test_duplicate_findings_share_one_inline_comment(self):
        data = bundle()
        for kind in ("code", "security"):
            data["results"][kind]["data"]["findings"] = [FINDING]
        api = FakeGitHub()
        _, passed = publish_review(api, data, CONTEXT)
        self.assertFalse(passed)
        self.assertEqual(len(api.posts[0][1]["comments"]), 1)

    def test_same_run_attempt_is_idempotent(self):
        api = FakeGitHub()
        first = publish_review(api, bundle(), CONTEXT)
        second = publish_review(api, bundle(), CONTEXT)
        self.assertEqual(first, second)
        self.assertEqual(len(api.posts), 1)

    def test_github_publication_failure_is_not_success(self):
        api = FakeGitHub()
        api.fail_post = True
        with self.assertRaises(ReviewError):
            publish_review(api, bundle(), CONTEXT)

    def test_incomplete_file_inventory_prevents_publication(self):
        api = FakeGitHub()
        api.pr["changed_files"] = 2
        with self.assertRaises(ReviewError):
            publish_review(api, bundle(), CONTEXT)
        self.assertEqual(api.posts, [])

    def test_model_text_is_data_and_cannot_create_mentions_or_images(self):
        data = bundle()
        data["results"]["code"]["data"]["summary"] = (
            "![image](https://example.invalid/x) @all <script>"
        )
        api = FakeGitHub()
        publish_review(api, data, CONTEXT)
        body = api.posts[0][1]["body"]
        self.assertNotIn("![image]", body)
        self.assertNotIn("@all", body)
        self.assertNotIn("<script>", body)


if __name__ == "__main__":
    unittest.main()
