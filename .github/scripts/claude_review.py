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

STAGES = ("review", "structure")
STAT_FIELDS = (
    "turns",
    "tool_calls",
    "subagent_tool_calls",
    "permission_denials",
    "cost_usd",
    "duration_ms",
)
BRIEF_INPUT_KEYS = {
    "Agent": "description",
    "Bash": "command",
    "Glob": "pattern",
    "Grep": "pattern",
    "Read": "file_path",
    "Task": "description",
}


class ReviewError(ValueError):
    """A controlled error that never includes model output or credentials."""


def text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ReviewError("Invalid text field in structured review")
    return value


def markdown(value):
    value = html.escape(value, quote=False).replace("@", "@​")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>\-])", r"\\\1", value)


def number(value):
    """Return a finite number from untrusted data, or None."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return value


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


def result_message(messages):
    """Return the official SDK result envelope, never an assistant's prose reply."""
    if not isinstance(messages, list):
        return None
    results = [
        message
        for message in messages
        if isinstance(message, dict) and message.get("type") == "result"
    ]
    return results[-1] if results else None


def brief_input(name, value):
    """Describe a tool call by its target only; never copy file contents or tool results."""
    if not isinstance(value, dict):
        return ""
    if name == "Skill":
        described = f"{value.get('skill', '')} {value.get('args', '')}".strip()
    else:
        key = BRIEF_INPUT_KEYS.get(name)
        described = value.get(key) if key else ""
    return described[:200] if isinstance(described, str) else ""


def diagnostics(messages):
    """Summarize a session as counts and a tool-call trace, without tool output or secrets."""
    summary = {
        "subtype": None,
        "is_error": None,
        "model": None,
        "turns": None,
        "duration_ms": None,
        "cost_usd": None,
        "tool_calls": 0,
        "subagent_tool_calls": 0,
        "permission_denials": 0,
        "tools": {},
        "trace": [],
        "denials": [],
    }
    if not isinstance(messages, list):
        return summary
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("type") == "system" and message.get("subtype") == "init":
            model = message.get("model")
            summary["model"] = model if isinstance(model, str) else None
        if message.get("type") != "assistant":
            continue
        nested = bool(message.get("parent_tool_use_id"))
        content = message.get("message", {})
        content = content.get("content") if isinstance(content, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name"))
            summary["tool_calls"] += 1
            summary["subagent_tool_calls"] += int(nested)
            summary["tools"][name] = summary["tools"].get(name, 0) + 1
            if len(summary["trace"]) < 300:
                scope = "sub" if nested else "main"
                summary["trace"].append([scope, name, brief_input(name, block.get("input"))])
    final = result_message(messages)
    if final is None:
        return summary
    summary["subtype"] = final.get("subtype") if isinstance(final.get("subtype"), str) else None
    summary["is_error"] = final.get("is_error") if isinstance(final.get("is_error"), bool) else None
    summary["turns"] = number(final.get("num_turns"))
    summary["duration_ms"] = number(final.get("duration_ms"))
    summary["cost_usd"] = number(final.get("total_cost_usd"))
    denials = final.get("permission_denials")
    if isinstance(denials, list):
        summary["permission_denials"] = len(denials)
        summary["denials"] = [
            [
                str(denial.get("tool_name")),
                brief_input(str(denial.get("tool_name")), denial.get("tool_input")),
            ]
            for denial in denials[:50]
            if isinstance(denial, dict)
        ]
    return summary


def extract_report(messages, outcome):
    """Review stage: the result text is the command's report; it must come from a real run."""
    summary = diagnostics(messages)

    def failed(reason):
        return {"outcome": "failure", "reason": reason, "report": None, "diagnostics": summary}

    if outcome != "success":
        return failed("review action step did not succeed")
    if not isinstance(messages, list):
        return failed("execution output is missing or malformed")
    final = result_message(messages)
    if final is None:
        return failed("no result envelope in execution output")
    if final.get("subtype") != "success" or final.get("is_error") is not False:
        return failed(
            f"result reported {final.get('subtype')!s} with is_error={final.get('is_error')!s}"
        )
    turns = number(final.get("num_turns"))
    if turns is None or turns < 1:
        return failed("result has no completed turns (authentication or startup failure)")
    report = final.get("result")
    if not isinstance(report, str) or not report.strip():
        return failed("result text is empty")
    return {
        "outcome": "success",
        "reason": "report captured",
        "report": report,
        "diagnostics": summary,
    }


def extract_result(messages, outcome):
    """Structuring stage: use the SDK structured_output, never an assistant's prose reply."""
    summary = diagnostics(messages)

    def failed(reason):
        return {"outcome": "failure", "reason": reason, "data": None, "diagnostics": summary}

    if outcome != "success":
        return failed("structuring action step did not succeed or was skipped")
    if not isinstance(messages, list):
        return failed("execution output is missing or malformed")
    final = result_message(messages)
    if final is None:
        return failed("no result envelope in execution output")
    if final.get("subtype") != "success" or final.get("is_error") is not False:
        return failed(
            f"result reported {final.get('subtype')!s} with is_error={final.get('is_error')!s}"
        )
    if final.get("permission_denials"):
        return failed("structuring pass requested a denied tool")
    if not isinstance(final.get("structured_output"), dict):
        return failed("no structured_output in result")
    return {
        "outcome": "success",
        "reason": "structured output captured",
        "data": final["structured_output"],
        "diagnostics": summary,
    }


def stats(summary):
    """Keep only numeric statistics for the published review and bundle."""
    if not isinstance(summary, dict):
        return {}
    values = {field: number(summary.get(field)) for field in STAT_FIELDS}
    return values if any(values.values()) else {}


def stats_line(stage, summary):
    values = stats(summary)
    if not any(value is not None for value in values.values()):
        return None

    def show(field, fmt="{}"):
        value = values[field]
        return "n/a" if value is None else fmt.format(value)

    duration = values["duration_ms"]
    return (
        f"{stage} stage: {show('turns')} turns, {show('tool_calls')} tool calls "
        f"({show('subagent_tool_calls')} in subagents), {show('permission_denials')} "
        f"permission denials, {show('cost_usd', '${:.2f}')}, "
        f"{'n/a' if duration is None else f'{duration / 1000:.0f} s'}"
    )


def step_summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a") as summary:
            summary.write("\n".join(lines) + "\n")


def load_messages():
    """Read the official action's execution file only from its expected location."""
    try:
        source = Path(os.environ["CLOAKMILL_EXECUTION_FILE"]).resolve()
        expected = (Path(os.environ["RUNNER_TEMP"]) / "claude-execution-output.json").resolve()
        if source == expected:
            return json.loads(source.read_text())
    except (KeyError, OSError, ValueError):
        pass
    return None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False))


def collect(kind, stage, output, report_path):
    results = output.parent
    outcome = os.environ.get("CLOAKMILL_ACTION_OUTCOME")
    messages = load_messages()
    if stage == "review":
        entry = extract_report(messages, outcome)
        write_json(results / "diagnostics" / f"{kind}-review.json", entry)
        if entry["outcome"] == "success" and report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(entry["report"])
        write_json(
            output,
            {
                "outcome": entry["outcome"],
                "reason": entry["reason"],
                "stats": stats(entry["diagnostics"]),
            },
        )
    else:
        entry = extract_result(messages, outcome)
        write_json(results / "diagnostics" / f"{kind}-structure.json", entry)
        try:
            review = json.loads((results / f"{kind}-review.json").read_text())
            review_stats = stats(review.get("stats"))
        except (OSError, ValueError, AttributeError):
            review_stats = {}
        write_json(
            output,
            {
                "outcome": entry["outcome"],
                "data": entry["data"],
                "diagnostics": {"review": review_stats, "structure": stats(entry["diagnostics"])},
            },
        )
    line = stats_line(stage, entry["diagnostics"]) or f"{stage} stage: no statistics recorded"
    step_summary(
        [
            f"**{kind} {stage}**: {entry['outcome']} ({entry['reason']}). {line}.",
            "",
        ]
    )
    print(
        f"{kind} {stage} stage: {entry['outcome']} ({entry['reason']}); "
        "raw session was not exported."
    )
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a") as handle:
            handle.write(f"outcome={entry['outcome']}\n")


def package_results(folder, context):
    bundle = {key: context[key] for key in ("repository", "number", "head_sha", "base_sha")}
    bundle["results"] = {}
    for kind in ("code", "security"):
        try:
            value = json.loads((folder / f"{kind}.json").read_text())
        except (OSError, ValueError):
            value = {"outcome": "failure", "data": None, "diagnostics": {}}
        bundle["results"][kind] = value
    return bundle


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


def pass_statistics(entry):
    """Render numeric stage statistics from the bundle; model text never reaches the review."""
    diagnostics_value = entry.get("diagnostics") if isinstance(entry, dict) else None
    if not isinstance(diagnostics_value, dict):
        return []
    lines = []
    for stage, label in (("review", "Review"), ("structure", "Structuring")):
        line = stats_line(label, diagnostics_value.get(stage))
        if line:
            lines.append(f"- {line}")
    return lines


def build_report(bundle, context, files):
    parsed = {}
    statistics = {}
    for kind in ("code", "security"):
        entry = bundle.get("results", {}).get(kind)
        statistics[kind] = pass_statistics(entry)
        try:
            if not isinstance(entry, dict) or entry.get("outcome") != "success":
                raise ReviewError("Review command failed or did not finish")
            value = validate_result(entry.get("data"), kind, context["head_sha"], files)
            parsed[kind] = value
        except ReviewError:
            parsed[kind] = {
                "status": "incomplete",
                "summary": (
                    "Structured review is missing or invalid. Inspect this pass in the Actions run "
                    "and its diagnostics artifact."
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
        body.extend(statistics[kind])
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
    parser.add_argument("--stage", choices=STAGES, default="structure")
    parser.add_argument(
        "--report", type=Path, help="where the review stage saves the command's report"
    )
    parser.add_argument("--package", action="store_true")
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    if args.collect:
        collect(args.collect, args.stage, args.bundle, args.report)
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
        if args.package:
            write_json(args.bundle, package_results(args.bundle.parent, context))
            return 0
        bundle = json.loads(args.bundle.read_text())
        api = GitHub(os.environ["GH_TOKEN"], os.environ["GITHUB_API_URL"])
        url, passed = publish_review(api, bundle, context)
    except (ReviewError, OSError, KeyError, ValueError):
        print(
            "::error::Review validation or publication failed. "
            "Check target revisions, structured results, and GitHub permissions."
        )
        return 1
    step_summary(
        [
            f"[Code and security review]({url})",
            "",
            "Both passes completed with no actionable findings."
            if passed
            else "Review has findings or is incomplete. Inspect the PR review before proceeding.",
        ]
    )
    if not passed:
        print(
            "::error::Review has actionable findings or is incomplete; see the published PR review."
        )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
