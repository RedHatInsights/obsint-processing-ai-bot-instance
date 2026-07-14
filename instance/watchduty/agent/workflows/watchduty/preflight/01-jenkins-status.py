#!/usr/bin/env python3
"""Pre-flight: fetch Jenkins job data BEFORE the AI session (zero tokens).

Filtering & priority (deterministic, no AI needed):
  1. Exclude disabled jobs (color contains "disabled")
  2. Exclude currently building jobs (latest build has result=null)
  3. Sort: prod before stage, failing before healthy

Exit conditions:
  - Both Jenkins instances unreachable -> skip (no tokens)
  - All eligible jobs healthy -> skip (nothing to report)
  - Failing jobs exist but ALL already tracked AND same error -> skip + send
    compact Slack message directly from preflight (zero tokens)
  - NEW failing jobs or error signature changed -> start (AI classifies)
"""

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path

MEMORY_SERVER = os.environ.get("MEMORY_SERVER_URL", "http://devbot-memory-server:8080")
INSTANCE_ID = os.environ.get("BOT_INSTANCE_ID", "")


def _find_skill_script():
    """Find triage_jenkins.py via PYTHONPATH (.claude/skills/) or relative path fallback."""
    for p in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        candidate = Path(p) / "triage-jenkins" / "triage_jenkins.py"
        if candidate.is_file():
            return candidate
    fallback = Path(__file__).resolve().parent.parent.parent.parent / "skills" / "triage-jenkins" / "triage_jenkins.py"
    if fallback.is_file():
        return fallback
    return None


def fetch_jenkins_data():
    skill_script = _find_skill_script()
    if skill_script is None:
        print("ERR: triage_jenkins.py not found", file=sys.stderr)
        return None
    try:
        proc = subprocess.run(
            [sys.executable, str(skill_script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def fetch_tracked_jobs():
    """Fetch active tasks from memory-server to find already-tracked failing jobs."""
    if not INSTANCE_ID:
        return set()
    try:
        params = urllib.parse.urlencode({
            "instance_id": INSTANCE_ID,
            "exclude_status": "archived",
            "limit": "100",
        })
        url = f"{MEMORY_SERVER}/api/tasks?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return {t["repo"] for t in data.get("tasks", []) if t.get("repo")}
    except Exception as e:
        print(f"WARN: could not fetch tracked tasks: {e}", file=sys.stderr)
        return set()


def fetch_stored_signatures():
    """Fetch stored error signatures from memory-server for tracked watchduty jobs.

    Returns {job_name: signature_hash} for entries tagged watchduty:jenkins:*.
    """
    signatures = {}
    try:
        params = urllib.parse.urlencode({
            "tag": "watchduty",
            "limit": "100",
        })
        url = f"{MEMORY_SERVER}/api/memories?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        for item in data.get("items", []):
            tags = item.get("tags", [])
            for tag in tags:
                if tag.startswith("watchduty:jenkins:"):
                    job_name = tag[len("watchduty:jenkins:"):]
                    content = item.get("content", "")
                    signatures[job_name] = _hash_content(content)
                    break
    except Exception as e:
        print(f"WARN: could not fetch stored signatures: {e}", file=sys.stderr)
    return signatures


def _hash_content(text):
    """Stable hash of text content for comparison."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def compute_current_signature(job):
    """Build a fingerprint from the latest failed build's error pattern.

    Uses failing stage names + failed test names from build data already
    fetched by triage_jenkins.py. Falls back to build number if no detail.
    """
    builds = job.get("builds", [])
    if not builds:
        return ""

    latest = builds[0]
    parts = []

    parts.append(f"result:{latest.get('result', 'UNKNOWN')}")

    detail = job.get("detail", {})
    if detail:
        stages = detail.get("stages", [])
        failed_stages = sorted(s["name"] for s in stages if s.get("status") != "SUCCESS")
        if failed_stages:
            parts.append(f"stages:{','.join(failed_stages)}")

        summary = detail.get("failure_summary", {})
        if summary:
            tests = sorted(summary.get("failed_tests", []))
            if tests:
                parts.append(f"tests:{','.join(tests)}")
            counts = summary.get("counts", "")
            if counts:
                parts.append(f"counts:{counts}")

        log_tail = detail.get("log_tail", "")
        if log_tail and not summary:
            tail_lines = [l.strip() for l in log_tail.strip().splitlines()[-5:] if l.strip()]
            parts.append(f"tail:{'|'.join(tail_lines)}")

    return _hash_content("|".join(parts))


def fetch_build_detail_for_job(job):
    """Fetch build detail for the latest failing build of a tracked job.

    Calls triage_jenkins.py <job-name> <build-num> to get failure details.
    """
    builds = job.get("builds", [])
    if not builds or builds[0].get("result") != "FAILURE":
        return

    skill_script = _find_skill_script()
    if skill_script is None:
        return

    build_num = builds[0]["number"]
    try:
        proc = subprocess.run(
            [sys.executable, str(skill_script), job["name"], str(build_num)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            if "detail" in data:
                job["detail"] = data["detail"]
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass


def send_compact_slack(head_failing, recovering, healthy, skipped, changed_jobs=None):
    """Send compact Slack message directly via webhook (zero AI tokens)."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        print("WARN: SLACK_WEBHOOK_URL not set, skipping compact message", file=sys.stderr)
        return False

    if changed_jobs:
        lines = ["CCX Jenkins Watchduty Report"]
    else:
        lines = ["CCX Jenkins Watchduty Report (no change)"]
    lines.append("")

    if head_failing:
        fail_names = ", ".join(j["name"] for j in head_failing)
        lines.append(f"FAILING ({len(head_failing)}): {fail_names}")
        if not changed_jobs:
            lines.append("  -- No new failures since last report, skipping AI analysis.")

    if recovering:
        lines.append(f"RECOVERING ({len(recovering)}): {', '.join(recovering)}")

    if healthy:
        if len(healthy) <= 8:
            lines.append(f"HEALTHY ({len(healthy)}): {', '.join(healthy)}")
        else:
            lines.append(f"HEALTHY ({len(healthy)}): {', '.join(healthy[:6])}, ...")

    building = [s["name"] for s in skipped if s.get("reason") == "building"]
    if building:
        lines.append(f"BUILDING ({len(building)}): {', '.join(building)}")

    msg = "\n".join(lines)

    try:
        payload = json.dumps({"msg": msg}).encode()
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"WARN: Slack webhook failed: {e}", file=sys.stderr)
        return False


def classify_jobs(data):
    jobs = data.get("jobs", [])
    if not jobs:
        return None, None, None, None, False

    eligible = []
    skipped = []

    for job in jobs:
        name = job.get("name", "")
        color = job.get("color", "")

        if "disabled" in color:
            skipped.append({"name": name, "reason": "disabled"})
            continue

        builds = job.get("builds", [])
        if builds and builds[0].get("result") is None:
            skipped.append({"name": name, "reason": "building"})
            continue

        recent_results = [b.get("result") for b in builds[:7]]
        fail_count = sum(1 for r in recent_results if r == "FAILURE")
        head_failing = recent_results[0] == "FAILURE" if recent_results else False

        is_prod = "prod" in name and "stage" not in name
        priority = (
            0 if head_failing and is_prod else
            1 if head_failing else
            2 if fail_count > 0 and is_prod else
            3 if fail_count > 0 else
            4 if is_prod else
            5
        )

        job["_priority"] = priority
        job["_fail_count"] = fail_count
        job["_head_failing"] = head_failing
        eligible.append(job)

    eligible.sort(key=lambda j: j["_priority"])

    head_failing = [j for j in eligible if j["_head_failing"]]
    recovering = [j["name"] for j in eligible if not j["_head_failing"] and j["_fail_count"] > 0]
    healthy = [j["name"] for j in eligible if not j["_head_failing"] and j["_fail_count"] == 0]

    return head_failing, recovering, healthy, skipped, len(head_failing) > 0


def main():
    data = fetch_jenkins_data()
    if data is None:
        json.dump(
            {"status": "skip", "content": "Pre-flight: both Jenkins instances unreachable. Skipping cycle."},
            sys.stdout,
        )
        return

    head_failing, recovering, healthy, skipped, has_failures = classify_jobs(data)
    if head_failing is None:
        json.dump(
            {"status": "skip", "content": "Pre-flight: no jobs returned from Jenkins. Skipping cycle."},
            sys.stdout,
        )
        return

    if not has_failures:
        total_ok = len(recovering) + len(healthy)
        json.dump(
            {"status": "skip", "content": f"Pre-flight: all {total_ok} eligible Jenkins jobs are healthy. Skipping cycle."},
            sys.stdout,
        )
        return

    tracked_jobs = fetch_tracked_jobs()
    failing_names = {j["name"] for j in head_failing}
    new_failures = failing_names - tracked_jobs

    if not new_failures:
        stored_sigs = fetch_stored_signatures()
        changed_jobs = []

        for job in head_failing:
            name = job["name"]
            if name not in stored_sigs:
                changed_jobs.append(name)
                continue

            fetch_build_detail_for_job(job)
            current_sig = compute_current_signature(job)
            if current_sig != stored_sigs[name]:
                changed_jobs.append(name)
                print(f"SIG CHANGE: {name} stored={stored_sigs[name]} current={current_sig}", file=sys.stderr)

        if not changed_jobs:
            sent = send_compact_slack(head_failing, recovering, healthy, skipped)
            status_msg = "compact Slack sent" if sent else "Slack skipped (no webhook)"
            json.dump(
                {"status": "skip", "content": f"Pre-flight: {len(head_failing)} failing (all tracked, same errors), {len(recovering)} recovering, {len(healthy)} healthy. {status_msg}."},
                sys.stdout,
            )
            return

        jobs_to_analyze = [j for j in head_failing if j["name"] in changed_jobs]
        still_tracked = [j["name"] for j in head_failing if j["name"] not in changed_jobs]

        header = f"Pre-flight: {len(jobs_to_analyze)} failing with CHANGED errors, {len(still_tracked)} tracked (same error), {len(recovering)} recovering, {len(healthy)} healthy.\n"
        header += "Error signature changed for these jobs — re-analyze and update memory.\n"
        header += "Do NOT re-run triage_jenkins.py for overview. Only fetch individual build details when analyzing a failure.\n\n"

        output = {
            "failing": jobs_to_analyze,
            "tracked_failing_jobs": still_tracked,
            "tracked_failing_count": len(still_tracked),
            "recovering_jobs": recovering,
            "recovering_count": len(recovering),
            "healthy_jobs": healthy,
            "healthy_count": len(healthy),
            "skipped": skipped,
            "errors": data.get("errors", []),
        }

        json.dump(
            {"status": "start", "content": header + json.dumps(output, indent=2)},
            sys.stdout,
        )
        return

    new_failing = [j for j in head_failing if j["name"] in new_failures]
    tracked_failing = [j["name"] for j in head_failing if j["name"] not in new_failures]

    header = f"Pre-flight: {len(new_failing)} NEW failing, {len(tracked_failing)} already tracked, {len(recovering)} recovering, {len(healthy)} healthy.\n"
    header += "Only NEW failures have full build data below. Already-tracked and recovering jobs are names only.\n"
    header += "Do NOT re-run triage_jenkins.py for overview. Only fetch individual build details when analyzing a failure.\n\n"

    output = {
        "failing": new_failing,
        "tracked_failing_jobs": tracked_failing,
        "tracked_failing_count": len(tracked_failing),
        "recovering_jobs": recovering,
        "recovering_count": len(recovering),
        "healthy_jobs": healthy,
        "healthy_count": len(healthy),
        "skipped": skipped,
        "errors": data.get("errors", []),
    }

    json.dump(
        {"status": "start", "content": header + json.dumps(output, indent=2)},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
