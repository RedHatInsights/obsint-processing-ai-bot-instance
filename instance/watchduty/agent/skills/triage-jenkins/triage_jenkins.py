#!/usr/bin/env python3
"""Fetch CCX Jenkins CI build data for agent-driven triage.

Thin data-fetching layer — returns structured JSON for the agent to analyze.
Pattern classification, known-issue matching, and recommendations live in SKILL.md.

Usage:
    python3 triage_jenkins.py                          # All active jobs + last 7 builds each
    python3 triage_jenkins.py <job-name>               # Single job, last 7 builds + failure detail
    python3 triage_jenkins.py <job-name> <build-num>   # Single build with stages + failure summary
    python3 triage_jenkins.py --builds 20              # More build history

Output is JSON to stdout.

Uses Python's urllib with corporate CA support via ssl.create_default_context.
"""

import argparse
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

def _ssl_context():
    return ssl.create_default_context(capath="/etc/pki/tls/certs/")

INSTANCES = {
    "qe": {
        "url": "https://jenkins-csb-insights-qe-main.dno.corp.redhat.com",
        "prefix": "/job/ccx",
    },
    "idp": {
        "url": "https://jenkins-csb-ccx-dev-main.dno.corp.redhat.com",
        "prefix": "",
    },
}

IDP_JOBS = {
    "internal-pipeline-tests-prod",
    "internal-pipeline-tests-stage",
    "internal-pipeline-test-rules-version-prod",
    "internal-pipeline-test-rules-version-stage",
    "ccx-load-test-stage",
}

errors = []


def _base(inst):
    return INSTANCES[inst]["url"] + INSTANCES[inst]["prefix"]


def _job_url(inst, job):
    return f"{_base(inst)}/job/{job}"


def instance_for_job(job):
    if job in IDP_JOBS:
        return "idp"
    return "qe"


def _fetch(url, params=None, timeout=10):
    if params:
        encoded = "&".join(
            f"{k}={urllib.parse.quote(v, safe='')}"
            for p in params
            for k, v in [p.split("=", 1)]
        )
        url = f"{url}?{encoded}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        errors.append(f"{url} http:{e.code}")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        errors.append(f"{url} error:{e}")
        return None


def fetch_json(url, params=None, timeout=10):
    body = _fetch(url, params, timeout)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        errors.append(f"{url} json_error")
        return None


def fetch_text(url, timeout=15):
    return _fetch(url, timeout=timeout)


def strip_class(obj):
    if isinstance(obj, dict):
        obj.pop("_class", None)
        for v in obj.values():
            strip_class(v)
    elif isinstance(obj, list):
        for item in obj:
            strip_class(item)


def add_time(builds):
    for b in builds:
        if b.get("timestamp"):
            b["time"] = datetime.fromtimestamp(
                b["timestamp"] / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")
    return builds


def get_all_jobs(n_builds=7):
    fields = "number,result,timestamp,duration"
    tree = (
        f"jobs[name,color,lastBuild[number],"
        f"lastFailedBuild[number],"
        f"builds[{fields}]{{{0},{n_builds}}}]"
    )
    all_jobs = []
    for inst_name, inst in INSTANCES.items():
        base = inst["url"] + inst["prefix"]
        data = fetch_json(f"{base}/api/json", [f"tree={tree}"])
        if not data:
            continue
        for j in data.get("jobs", []):
            add_time(j.get("builds", []))
            j["instance"] = inst_name
        strip_class(data)
        all_jobs.extend(data.get("jobs", []))
    return {"jobs": all_jobs} if all_jobs else None


def get_job_builds(job, n_builds=7):
    inst = instance_for_job(job)
    fields = "number,result,timestamp,duration"
    tree = (
        f"name,color,lastBuild[number],"
        f"lastFailedBuild[number],"
        f"builds[{fields}]{{{0},{n_builds}}}"
    )
    data = fetch_json(f"{_job_url(inst, job)}/api/json", [f"tree={tree}"])
    if not data:
        return None
    data["instance"] = inst
    add_time(data.get("builds", []))
    strip_class(data)
    return data


def get_build_detail(job, build_num):
    inst = instance_for_job(job)
    base = _job_url(inst, job)
    detail = {"build": build_num, "stages": [], "failure_summary": None}

    stages_data = fetch_json(f"{base}/{build_num}/wfapi/describe")
    if stages_data:
        detail["stages"] = [
            {
                "name": s["name"],
                "status": s["status"],
                "duration_s": round(s.get("durationMillis", 0) / 1000),
            }
            for s in stages_data.get("stages", [])
        ]

    log = fetch_text(f"{base}/{build_num}/consoleText")
    if log:
        failed_tests = []
        counts = None
        in_summary = False
        for line in log.splitlines():
            if "short test summary info" in line:
                in_summary = True
                continue
            if in_summary:
                if line.startswith("=") and ("passed" in line or "failed" in line):
                    counts = line.strip().strip("= ")
                    break
                if line.startswith("FAILED "):
                    failed_tests.append(line.strip())
        if failed_tests or counts:
            detail["failure_summary"] = {
                "failed_tests": failed_tests,
                "counts": counts,
            }
        else:
            tail = log.strip().splitlines()[-50:]
            detail["log_tail"] = "\n".join(tail)

    return detail


def parse_job_from_url(url):
    m = re.search(r"/job/ccx/job/([^/]+?)(?:/(\d+))?(?:/|$)", url)
    if not m:
        m = re.search(r"ccx%2F([^/]+?)(?:/|$)", url)
    if not m:
        m = re.search(
            r"jenkins-csb-ccx-dev-main[^/]*/job/([^/]+?)(?:/(\d+))?(?:/|$)",
            url,
        )
    if m:
        return (
            m.group(1),
            int(m.group(2)) if m.lastindex >= 2 and m.group(2) else None,
        )
    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch CCX Jenkins build data for triage."
    )
    parser.add_argument("job", nargs="?", help="Job name or full Jenkins URL")
    parser.add_argument("build", nargs="?", type=int, help="Build number")
    parser.add_argument(
        "--builds",
        type=int,
        default=None,
        help="Number of builds to fetch",
    )
    args = parser.parse_args()

    if args.job:
        job, build = args.job, args.build
        parsed_job, parsed_build = parse_job_from_url(job)
        if parsed_job:
            job, build = parsed_job, parsed_build or build

        result = get_job_builds(job, n_builds=args.builds or 7)
        if not result:
            result = {}
        else:
            target = build
            if not target:
                failed = [
                    b for b in result.get("builds", []) if b.get("result") == "FAILURE"
                ]
                if failed:
                    target = failed[0]["number"]
            if target:
                result["detail"] = get_build_detail(job, target)
    else:
        result = get_all_jobs(n_builds=args.builds or 10)
        if not result:
            result = {}

    if errors:
        result["errors"] = errors

    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
