#!/usr/bin/env python3
"""Pre-flight: fetch Jenkins job data BEFORE the AI session (zero tokens).

Filtering & priority (deterministic, no AI needed):
  1. Exclude disabled jobs (color contains "disabled")
  2. Exclude currently building jobs (latest build has result=null)
  3. Sort: prod before stage, failing before healthy

Exit conditions:
  - Both Jenkins instances unreachable -> skip (no tokens)
  - All eligible jobs healthy -> skip (nothing to report)
  - At least one eligible job failing -> start (AI classifies and reports)
"""

import json
import os
import subprocess
import sys
from pathlib import Path


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


def classify_jobs(data):
    jobs = data.get("jobs", [])
    if not jobs:
        return None, None, False

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

    failing = [j for j in eligible if j["_head_failing"] or j["_fail_count"] > 0]
    healthy = [j["name"] for j in eligible if not j["_head_failing"] and j["_fail_count"] == 0]

    return failing, healthy, skipped, len(failing) > 0


def main():
    data = fetch_jenkins_data()
    if data is None:
        json.dump(
            {"status": "skip", "content": "Pre-flight: both Jenkins instances unreachable. Skipping cycle."},
            sys.stdout,
        )
        return

    failing, healthy, skipped, has_failures = classify_jobs(data)
    if failing is None:
        json.dump(
            {"status": "skip", "content": "Pre-flight: no jobs returned from Jenkins. Skipping cycle."},
            sys.stdout,
        )
        return

    if not has_failures:
        json.dump(
            {"status": "skip", "content": f"Pre-flight: all {len(healthy)} eligible Jenkins jobs are healthy. Skipping cycle."},
            sys.stdout,
        )
        return

    head_failing_count = sum(1 for j in failing if j["_head_failing"])

    header = f"Pre-flight: {head_failing_count} currently failing, {len(failing)} with recent failures, {len(healthy)} healthy.\n"
    header += "Only failing jobs included below — healthy jobs are omitted to save tokens.\n"
    header += "Do NOT re-run triage_jenkins.py for overview. Only fetch individual build details when analyzing a failure.\n\n"

    output = {
        "failing": failing,
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
