"""Validate and publish Claude review data. This is CI tooling, not product runtime."""

import argparse
import html
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class ReviewError(ValueError):
    """A controlled error that never includes model output or credentials."""


def text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ReviewError("Invalid text field in structured review")
    return value


def markdown(value):
    value = html.escape(value, quote=False).replace("@", "@\u200b")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", value)


def added_lines(patch):
    """Return actual added RIGHT-side anchors from a GitHub file patch."""
    lines = set()
    current = None
    for line in (patch or "").splitlines():
        match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if match:
            current = int(match[1])
        elif current is not None and line.startswith("+"):
            lines.add(current)
            current += 1
        elif current is not None and line.startswith(" "):
            current += 1
    return lines


def extract_result(messages, outcome):
    """Use the official SDK result envelope, never an assistant's prose reply."""
    failed = {"outcome": "failure", "data": None}
    if outcome != "success" or not isinstance(messages, list):
        return failed
    results = [
        message
        for message in messages
        if isinstance(message, dict) and message.get("type") == "result"
    ]
    if not results:
        return failed
    final = results[-1]
    if (
        final.get("subtype") != "success"
        or final.get("is_error") is not False
        or final.get("permission_denials")
        or not isinstance(final.get("structured_output"), dict)
    ):
        return failed
    return {"outcome": "success", "data": final["structured_output"]}


def validate_result(value, kind, head, files):
    fields = {"review_type", "reviewed_head", "status", "summary", "findings", "limitations"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ReviewError("Missing or malformed structured review")
    if value["review_type"] != kind or value["reviewed_head"] != head:
        raise ReviewError("Structured review targets the wrong pass or commit")
    if value["status"] not in ("completed", "incomplete"):
        raise ReviewError("Invalid completion status")
    text(value["summary"], 4000)
    limits = value["limitations"]
    if not isinstance(limits, list) or not 1 <= len(limits) <= 10:
        raise ReviewError("Review limitations must be explicit")
    for limit in limits:
        text(limit, 1000)
    findings = value["findings"]
    if not isinstance(findings, list) or len(findings) > 20:
        raise ReviewError("Invalid findings list")
    required = {
        "path",
        "line",
        "severity",
        "confidence",
        "title",
        "explanation",
        "evidence",
        "recommendation",
    }
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != required:
            raise ReviewError("Invalid finding fields")
        path, line = finding["path"], finding["line"]
        if (
            not isinstance(path, str)
            or path not in files
            or any(part in ("", ".", "..") for part in path.split("/"))
            or type(line) is not int
            or line not in files[path]
        ):
            raise ReviewError("Finding must reference an added line in this PR")
        severity, confidence = finding["severity"], finding["confidence"]
        if severity not in ("low", "medium", "high", "critical"):
            raise ReviewError("Invalid severity")
        if kind == "security" and severity == "low":
            raise ReviewError("Security findings must have concrete medium-or-higher impact")
        if (
            type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0.8 <= confidence <= 1
        ):
            raise ReviewError("Finding confidence is insufficient or invalid")
        for field, maximum in (
            ("title", 180),
            ("explanation", 2000),
            ("evidence", 1500),
            ("recommendation", 1500),
        ):
            text(finding[field], maximum)
    return value


def validate_target(pr, context):
    repo = context["repository"]
    if (
        pr.get("state") != "open"
        or pr.get("draft") is not False
        or (pr.get("head", {}).get("repo") or {}).get("full_name") != repo
        or (pr.get("base", {}).get("repo") or {}).get("full_name") != repo
    ):
        raise ReviewError("Review target is no longer an open, ready, same-repository PR")
    if pr["head"].get("sha") != context["head_sha"] or pr["base"].get("sha") != context["base_sha"]:
        raise ReviewError("PR head or base changed during review; rerun for the current revisions")


def build_report(bundle, context, files):
    parsed = {}
    for kind in ("code", "security"):
        entry = bundle.get("results", {}).get(kind)
        try:
            if not isinstance(entry, dict) or entry.get("outcome") != "success":
                raise ReviewError("Review command failed or did not finish")
            value = validate_result(entry.get("data"), kind, context["head_sha"], files)
            parsed[kind] = value
        except ReviewError:
            parsed[kind] = {
                "status": "incomplete",
                "summary": (
                    "Structured review is missing or invalid. Inspect this pass in the Actions run."
                ),
                "findings": [],
                "limitations": ["This pass has no validated completed result."],
            }
    complete = all(value["status"] == "completed" for value in parsed.values())
    unique = {}
    for kind, value in parsed.items():
        if value["status"] != "completed":
            continue
        for finding in value["findings"]:
            key = (finding["path"], finding["line"], finding["title"])
            unique.setdefault(key, (kind, finding))
    status = "incomplete" if not complete else "findings" if unique else "no-actionable-findings"
    marker = f"<!-- cloakmill-claude-review:{context['run_id']}:{context['run_attempt']} -->"
    run = f"{context['server_url']}/{context['repository']}/actions/runs/{context['run_id']}"
    body = [
        marker,
        "## CloakMill code and security review",
        "",
        f"Reviewed head: `{context['head_sha']}`",
        f"Reviewed base: `{context['base_sha']}`",
        f"[Actions run]({run})",
        "",
        f"Review-Result: {status}",
        "",
    ]
    for kind, title in (("code", "Code review"), ("security", "Security review")):
        value = parsed[kind]
        body.extend([f"### {title}: {value['status']}", "", markdown(value["summary"]), ""])
        body.extend(f"- {markdown(limit)}" for limit in value["limitations"])
        body.append("")
    comments = []
    if unique:
        body.extend(["### Findings", ""])
    for kind, finding in unique.values():
        path, line = finding["path"], finding["line"]
        url = (
            f"{context['server_url']}/{context['repository']}/blob/{context['head_sha']}/"
            f"{urllib.parse.quote(path, safe='/')}#L{line}"
        )
        body.append(
            f"- **{finding['severity'].upper()} · {kind}**: {markdown(finding['title'])} "
            f"([source]({url}))"
        )
        content = [
            f"**{finding['severity'].upper()} · {kind}: {markdown(finding['title'])}**",
            "",
            markdown(finding["explanation"]),
            "",
            "**Evidence / trigger**",
            markdown(finding["evidence"]),
            "",
            "**Recommendation**",
            markdown(finding["recommendation"]),
            "",
            f"Confidence: {finding['confidence']:.0%}. Reviewed head: `{context['head_sha']}`.",
        ]
        comments.append({"path": path, "line": line, "side": "RIGHT", "body": "\n".join(content)})
    body.extend(
        [
            "",
            "Source review only. Project test results are reported by CI separately. "
            "No findings does not guarantee correctness or security. "
            "This review does not approve or merge the PR.",
        ]
    )
    payload = {"commit_id": context["head_sha"], "event": "COMMENT", "body": "\n".join(body)}
    if comments:
        payload["comments"] = comments
    return payload, complete and not unique, marker


def publish_review(api, bundle, context):
    repo = context["repository"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ReviewError("Invalid repository")
    if type(context["number"]) is not int or context["number"] < 1:
        raise ReviewError("Invalid PR number")
    for key in ("head_sha", "base_sha"):
        if not re.fullmatch(r"[0-9a-f]{40}", context[key]):
            raise ReviewError("Invalid revision")
    if not isinstance(bundle, dict) or any(
        bundle.get(key) != context[key] for key in ("repository", "number", "head_sha", "base_sha")
    ):
        raise ReviewError("Result bundle does not match the expected target")
    prefix = f"/repos/{repo}/pulls/{context['number']}"
    pr = api.get(prefix)
    validate_target(pr, context)
    inventory = api.paginate(f"{prefix}/files")
    if len(inventory) != pr.get("changed_files"):
        raise ReviewError("Incomplete changed-file inventory; review coverage cannot be verified")
    files = {item["filename"]: added_lines(item.get("patch")) for item in inventory}
    payload, passed, marker = build_report(bundle, context, files)
    matches = [
        review
        for review in api.paginate(f"{prefix}/reviews")
        if review.get("user", {}).get("login") == "github-actions[bot]"
        and marker in review.get("body", "")
    ]
    validate_target(api.get(prefix), context)
    if matches:
        review = matches[-1]
        if review.get("body") != payload["body"]:
            raise ReviewError("This run attempt already published a different result")
    else:
        review = api.post(f"{prefix}/reviews", payload)
    verified = api.get(f"{prefix}/reviews/{review['id']}")
    if (
        verified.get("body") != payload["body"]
        or verified.get("commit_id") != context["head_sha"]
        or verified.get("state") != "COMMENTED"
        or verified.get("user", {}).get("login") != "github-actions[bot]"
    ):
        raise ReviewError("GitHub did not confirm the expected review publication")
    validate_target(api.get(prefix), context)
    return verified["html_url"], passed


class GitHub:
    def __init__(self, token, base_url):
        self.token = token
        self.base_url = base_url.rstrip("/")

    def request(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ReviewError(f"GitHub API {method} failed with HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            raise ReviewError("GitHub API request or response failed") from None

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, payload):
        return self.request("POST", path, payload)

    def paginate(self, path):
        items = []
        for page in range(1, 101):
            batch = self.get(f"{path}?per_page=100&page={page}")
            if not isinstance(batch, list):
                raise ReviewError("Invalid paginated GitHub response")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise ReviewError("GitHub response exceeded the supported pagination bound")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect", choices=("code", "security"))
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    if args.collect:
        messages = None
        try:
            source = Path(os.environ["CLOAKMILL_EXECUTION_FILE"]).resolve()
            expected = (Path(os.environ["RUNNER_TEMP"]) / "claude-execution-output.json").resolve()
            if source == expected:
                messages = json.loads(source.read_text())
        except (KeyError, OSError, ValueError):
            pass
        entry = extract_result(messages, os.environ.get("CLOAKMILL_ACTION_OUTCOME"))
        args.bundle.write_text(json.dumps(entry, allow_nan=False))
        print(
            f"{args.collect} structured result: {entry['outcome']}; raw session was not exported."
        )
        return 0
    try:
        context = {
            "repository": os.environ["GITHUB_REPOSITORY"],
            "number": int(os.environ["CLOAKMILL_PR_NUMBER"]),
            "head_sha": os.environ["CLOAKMILL_REVIEW_HEAD"],
            "base_sha": os.environ["CLOAKMILL_REVIEW_BASE"],
            "run_id": int(os.environ["GITHUB_RUN_ID"]),
            "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
            "server_url": os.environ["GITHUB_SERVER_URL"],
        }
        bundle = json.loads(args.bundle.read_text())
        api = GitHub(os.environ["GH_TOKEN"], os.environ["GITHUB_API_URL"])
        url, passed = publish_review(api, bundle, context)
    except (ReviewError, OSError, KeyError, ValueError):
        print(
            "::error::Review validation or publication failed. "
            "Check target revisions, structured results, and GitHub permissions."
        )
        return 1
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
        summary.write(f"[Code and security review]({url})\n\n")
        summary.write(
            "Both passes completed with no actionable findings.\n"
            if passed
            else "Review has findings or is incomplete. Inspect the PR review before proceeding.\n"
        )
    if not passed:
        print(
            "::error::Review has actionable findings or is incomplete; see the published PR review."
        )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
