#!/usr/bin/env python3
"""Check CI before the agent sends a GitHub PR review notification.

Read CI through the runner's proxy-backed gh client. Pending checks return
immediately so Rehor can schedule another cycle. Success needs two matching
observations, 30 seconds apart by default. Print the result as JSON; the agent
owns task metadata, CI retries, and Slack delivery.
"""

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Collection
from urllib.parse import urlparse


EXIT_CODES = {
    "passed": 0,
    "failed": 1,
    "error": 2,
    "pending": 3,
    "blocked": 4,
}
CLI_TIMEOUT_SECONDS = 45
DEFAULT_CONFIRM_SECONDS = 30

PENDING = {"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED"}
FAILED = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}


def validate_pr_url(pr: str) -> None:
    """Require an explicit GitHub PR URL, independent of the local checkout."""
    url = urlparse(pr)
    parts = url.path.strip("/").split("/")
    if (
        url.scheme != "https"
        or url.netloc != "github.com"
        or url.query
        or url.fragment
        or len(parts) != 4
        or not all(parts)
        or parts[2] != "pull"
        or not parts[3].isdigit()
    ):
        raise ValueError("Use a full HTTPS GitHub /pull/NUMBER URL; GitLab MRs do not use this gate")


def cli_json(command: list[str]):
    """Run a bounded proxy CLI request without handling credentials ourselves."""
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT_SECONDS,
    )
    if result.returncode:
        # Do not echo arbitrary CLI output (which can include sensitive data).
        raise ValueError(
            f"{command[0]} query failed (exit {result.returncode}); check authentication/access"
        )
    return json.loads(result.stdout)


def github_check_row(check: dict) -> dict:
    """Normalize either a GitHub check run or an external commit status."""
    if not isinstance(check, dict):
        raise ValueError("Invalid check response")

    kind = check.get("__typename")
    if kind == "CheckRun":
        name = check.get("name")
        status = check.get("status")
        # A conclusion is meaningful only after the check finishes.
        state = check.get("conclusion") if status == "COMPLETED" else status
        link = check.get("detailsUrl")
    elif kind == "StatusContext":
        name = check.get("context")
        state = check.get("state")
        link = check.get("targetUrl")
    else:
        raise ValueError("Unknown check type")

    if not isinstance(name, str) or not name or not isinstance(state, str) or not state:
        raise ValueError("Check name/state missing")
    return {"name": name, "state": state, "url": link}


def inspect_pr(pr: str, expected: Collection[str]) -> dict:
    """Read the PR head and its checks together, including external CI statuses."""
    validate_pr_url(pr)
    data = cli_json(["gh", "pr", "view", pr, "--json", "headRefOid,state,statusCheckRollup"])
    if not isinstance(data, dict) or not data.get("headRefOid") or not data.get("state"):
        raise ValueError("Incomplete PR response")
    checks = data.get("statusCheckRollup")
    if not isinstance(checks, list):
        raise ValueError("Missing or invalid statusCheckRollup")
    rows = [github_check_row(check) for check in checks]
    return evaluate(pr, data["headRefOid"], data["state"] == "OPEN", rows, expected)


def evaluate(
    pr: str, sha: str, is_open: bool, rows: list[dict], expected: Collection[str]
) -> dict:
    """Classify a snapshot; completed skipped checks count as passing."""
    missing = sorted(set(expected) - {row["name"] for row in rows})
    waiting_on = None

    # Wait for running checks before treating failures as the final CI outcome.
    # Once nothing is running, report known failures even if other checks are missing.
    if not is_open:
        status = "blocked"
        reason = "PR is no longer open"
    elif any(row["state"] in PENDING for row in rows):
        status = "pending"
        reason = "Checks are still running"
        waiting_on = "running"
    elif any(row["state"] in FAILED for row in rows):
        status = "failed"
        reason = "CI finished with failures"
    elif not rows or missing:
        status = "pending"
        reason = "Checks are missing"
        waiting_on = "missing"
    elif any(row["state"] not in {"SUCCESS", "SKIPPED"} for row in rows):
        status = "blocked"
        reason = "Neutral or unknown results are not proof of passing CI"
    else:
        status = "passed"
        reason = "All reported and explicitly expected checks succeeded or were skipped"

    return {
        "status": status,
        "reason": reason,
        "pr": pr,
        "head_sha": sha,
        "is_open": is_open,
        "checks": rows,
        "missing_checks": missing,
        "waiting_on": waiting_on,
    }


def snapshot_fingerprint(result: dict) -> tuple[str, str]:
    """Compare the head and check results independently of API response ordering."""
    checks = sorted(result["checks"], key=lambda row: (row["name"], row["url"] or ""))
    return result["head_sha"], json.dumps(checks, sort_keys=True)


def wait_for_ci(
    pr: str, expected: Collection[str] = (), confirm_after: int = DEFAULT_CONFIRM_SECONDS
) -> dict:
    """Check once; only a green result needs a second observation before sending."""
    try:
        first = inspect_pr(pr, expected)
        if first["status"] != "passed":
            return first

        time.sleep(confirm_after)
        second = inspect_pr(pr, expected)
        if second["status"] == "passed" and snapshot_fingerprint(first) != snapshot_fingerprint(second):
            return {
                **second,
                "status": "pending",
                "waiting_on": "confirming",
                "reason": "Commit or checks changed; confirm again next cycle",
            }
        return second
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"status": "error", "pr": pr, "reason": str(exc)}


def review_action(result: dict) -> str:
    """A broken checker must not hide a review request or imply CI success."""
    if result.get("is_open") is False:
        return "none"
    status = result["status"]
    if status == "passed":
        return "ready"
    if status == "failed":
        return "investigate_failure"
    if status in {"error", "blocked"}:
        return "review_unverified"
    # Rehor owns the grace period for missing checks across scheduled cycles.
    return "defer"


def parse_args() -> argparse.Namespace:
    """Validate command-line input before making any provider requests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", help="Full upstream GitHub PR URL")
    parser.add_argument(
        "--expect-check", action="append", default=[], help="Expected check name; repeatable"
    )
    parser.add_argument(
        "--confirm-after", type=int, default=DEFAULT_CONFIRM_SECONDS,
        help="Seconds before confirming a green result (default: 30)",
    )
    args = parser.parse_args()
    try:
        validate_pr_url(args.pr)
    except ValueError as exc:
        parser.error(str(exc))
    if args.confirm_after <= 0:
        parser.error("--confirm-after must be positive")
    return args


def main() -> int:
    """Run the gate and emit its result, review action, and exit code."""
    args = parse_args()
    result = wait_for_ci(args.pr, args.expect_check, args.confirm_after)
    result["review_action"] = review_action(result)
    print(json.dumps(result))
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
