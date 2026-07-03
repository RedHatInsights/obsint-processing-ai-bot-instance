#!/bin/bash
# Pre-flight: fetch Jenkins job data BEFORE the AI session (zero tokens).
#
# - If at least one Jenkins instance responds: return "start" with the
#   fetched JSON as content so the AI skips the data-fetching step.
# - If both instances are unreachable: return "skip" — no point burning
#   tokens when there's nothing to analyze.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/../../skills/triage-jenkins"

# Try to fetch all jobs (the script outputs JSON to stdout)
jenkins_data=$(python3 "$SKILL_DIR/triage_jenkins.py" 2>/dev/null)
exit_code=$?

# Check if we got valid data
if [ $exit_code -ne 0 ] || [ -z "$jenkins_data" ]; then
    cat <<'EOF'
{"status": "skip", "content": "Pre-flight: both Jenkins instances unreachable. Skipping cycle."}
EOF
    exit 0
fi

# Check if any jobs were returned
has_jobs=$(echo "$jenkins_data" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    jobs = data.get('jobs', [])
    print('yes' if jobs else 'no')
except:
    print('no')
" 2>/dev/null)

if [ "$has_jobs" != "yes" ]; then
    cat <<'EOF'
{"status": "skip", "content": "Pre-flight: no jobs returned from Jenkins. Skipping cycle."}
EOF
    exit 0
fi

# We have data — pass it to the AI session as pre-fetched context
# Escape the JSON for embedding in the content field
escaped_data=$(echo "$jenkins_data" | python3 -c "
import json, sys
data = sys.stdin.read()
result = {
    'status': 'start',
    'content': 'Pre-flight fetched Jenkins data. Use this instead of running triage_jenkins.py again for the overview. Run it only for individual build details when needed.\n\n' + data
}
json.dump(result, sys.stdout)
")

echo "$escaped_data"
