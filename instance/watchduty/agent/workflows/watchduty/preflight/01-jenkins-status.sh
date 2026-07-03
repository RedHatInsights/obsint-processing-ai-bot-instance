#!/bin/bash
# Pre-flight: fetch Jenkins job data BEFORE the AI session (zero tokens).
#
# Filtering & priority (deterministic, no AI needed):
#   1. Exclude disabled jobs (color contains "disabled")
#   2. Exclude currently building jobs (latest build has result=null)
#   3. Sort: prod before stage, failing before healthy
#
# Exit conditions:
#   - Both Jenkins instances unreachable → skip (no tokens)
#   - All eligible jobs healthy → skip (nothing to report)
#   - At least one eligible job failing → start (AI classifies and reports)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/../../.."
SKILL_DIR="$AGENT_DIR/skills/triage-jenkins"

jenkins_data=$(python3 "$SKILL_DIR/triage_jenkins.py" 2>/dev/null)
exit_code=$?

if [ $exit_code -ne 0 ] || [ -z "$jenkins_data" ]; then
    cat <<'EOF'
{"status": "skip", "content": "Pre-flight: both Jenkins instances unreachable. Skipping cycle."}
EOF
    exit 0
fi

# Filter, classify, and prioritize — all deterministic
echo "$jenkins_data" | python3 -c "
import json, sys

data = json.load(sys.stdin)
jobs = data.get('jobs', [])

if not jobs:
    json.dump({'status': 'skip', 'content': 'Pre-flight: no jobs returned from Jenkins. Skipping cycle.'}, sys.stdout)
    sys.exit(0)

eligible = []
skipped = []

for job in jobs:
    name = job.get('name', '')
    color = job.get('color', '')

    # Skip disabled jobs
    if 'disabled' in color:
        skipped.append({'name': name, 'reason': 'disabled'})
        continue

    # Skip jobs whose latest build is still running (result=null)
    builds = job.get('builds', [])
    if builds and builds[0].get('result') is None:
        skipped.append({'name': name, 'reason': 'building'})
        continue

    # Classify: count recent failures for priority sorting
    recent_results = [b.get('result') for b in builds[:7]]
    fail_count = sum(1 for r in recent_results if r == 'FAILURE')
    head_failing = recent_results[0] == 'FAILURE' if recent_results else False

    # Priority: prod > stage, head-failing > historical failures > healthy
    is_prod = 'prod' in name and 'stage' not in name
    priority = (
        0 if head_failing and is_prod else
        1 if head_failing else
        2 if fail_count > 0 and is_prod else
        3 if fail_count > 0 else
        4 if is_prod else
        5
    )

    job['_priority'] = priority
    job['_fail_count'] = fail_count
    job['_head_failing'] = head_failing
    eligible.append(job)

eligible.sort(key=lambda j: j['_priority'])

has_failures = any(j['_head_failing'] or j['_fail_count'] > 0 for j in eligible)

summary_parts = []
if skipped:
    summary_parts.append(f'Filtered out {len(skipped)} ineligible jobs ({', '.join(s[\"reason\"] for s in skipped)})')
summary_parts.append(f'{len(eligible)} eligible jobs')
if has_failures:
    failing_count = sum(1 for j in eligible if j['_head_failing'])
    summary_parts.append(f'{failing_count} currently failing')

header = 'Pre-flight Jenkins data (filtered and prioritized). '
header += '. '.join(summary_parts) + '.\n'
header += 'Jobs are sorted: prod-failing first, then stage-failing, then healthy.\n'
header += 'Do NOT re-run triage_jenkins.py for overview. Only fetch individual build details when analyzing a failure.\n\n'

output = {
    'eligible': eligible,
    'skipped': skipped,
    'errors': data.get('errors', []),
}

result = {
    'status': 'start' if has_failures else 'skip',
    'content': header + json.dumps(output, indent=2) if has_failures else 'Pre-flight: all ' + str(len(eligible)) + ' eligible Jenkins jobs are healthy. Skipping cycle.',
}
json.dump(result, sys.stdout)
"
