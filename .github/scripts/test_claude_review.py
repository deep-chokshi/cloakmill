"""Behavioral tests for the review publisher; no model or network is used."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from claude_review import ReviewError, extract_result, package_results, publish_review

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
            kind: {"outcome": "success", "data": result(kind)} for kind in ("code", "security")
        },
    }


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


class ReviewPublisherTests(unittest.TestCase):
    def test_a_completed_json_claim_without_running_the_command_is_rejected(self):
        messages = [
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": result("code"),
            }
        ]
        self.assertEqual(extract_result(messages, "success", "code-review")["outcome"], "failure")

    def test_command_invocation_and_successful_return_are_required(self):
        messages = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Skill",
                            "id": "review-call",
                            "input": {"skill": "code-review", "args": "high base...head"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "review-call", "content": "Report"}
                    ]
                },
            },
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": result("code"),
            },
        ]
        self.assertEqual(extract_result(messages, "success", "code-review")["outcome"], "success")
        messages[1]["message"]["content"][0]["is_error"] = True
        self.assertEqual(extract_result(messages, "success", "code-review")["outcome"], "failure")

    def test_missing_security_file_packages_as_incomplete_for_visible_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "code.json").write_text(
                json.dumps({"outcome": "success", "data": result("code")})
            )
            data = package_results(folder, CONTEXT)
            self.assertEqual(data["results"]["security"]["outcome"], "failure")
            api = FakeGitHub()
            _, passed = publish_review(api, data, CONTEXT)
            self.assertFalse(passed)
            self.assertIn("Security review: incomplete", api.posts[0][1]["body"])

    def test_success_without_structured_findings_is_incomplete(self):
        entry = extract_result(
            [{"type": "result", "subtype": "success", "is_error": False}], "success"
        )
        self.assertEqual(entry["outcome"], "failure")

    def test_only_validated_structured_data_is_extracted_not_raw_session(self):
        messages = [
            {"type": "assistant", "message": {"content": "synthetic-private-session"}},
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "structured_output": result("code"),
                "permission_denials": [],
            },
        ]
        self.assertEqual(
            extract_result(messages, "success"), {"outcome": "success", "data": result("code")}
        )

    def test_budget_errors_denials_and_action_failure_never_become_clean(self):
        base = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "structured_output": result("code"),
        }
        for override, outcome in (
            ({"subtype": "error_max_budget_usd"}, "success"),
            ({"is_error": True}, "success"),
            ({"permission_denials": [{"tool_name": "Bash"}]}, "success"),
            ({}, "failure"),
        ):
            with self.subTest(override=override, outcome=outcome):
                self.assertEqual(
                    extract_result([dict(base, **override)], outcome)["outcome"], "failure"
                )

    def test_empty_or_malformed_execution_data_is_incomplete(self):
        for value in ([], {}, None, ["invalid"]):
            self.assertEqual(extract_result(value, "success")["outcome"], "failure")

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
