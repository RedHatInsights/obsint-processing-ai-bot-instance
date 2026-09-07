#!/usr/bin/env python3
"""GlitchTip API client via the proxy endpoint.

All requests go through the devbot-proxy GlitchTip reverse proxy
(GLITCHTIP_API_URL). The proxy injects the Bearer token — this script
never handles credentials. Mirrors the gh-release-upload skill pattern:
a committed script using urllib (bash curl/wget are blocked by the
security hook; HTTP one-liners are blocked too, but script files are allowed).
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("GLITCHTIP_API_URL", "http://devbot-proxy:8448").rstrip("/")
ORG = os.environ.get("GLITCHTIP_ORG", "ccx")
TIMEOUT = 30

USAGE = """Usage: glitchtip.py <command> [args]

Commands:
  list [--project ID] [--query Q] [--limit N]
        List issues for the organization (default query: is:unresolved).
  issue <issue-id>
        Get a single issue by numeric ID.
  latest <issue-id>
        Get the latest event for an issue (full stacktrace).
  events <issue-id> [--limit N]
        List recent events for an issue.
  resolve <issue-id>
        Mark an issue as resolved.

All output is pretty-printed JSON on stdout. Errors go to stderr with a
non-zero exit code. Auth is handled by the proxy — never pass a token.
"""


def _request(path, method="GET", body=None):
    url = BASE_URL + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode()
            if not raw:
                return {"status": resp.status}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        detail = e.read().decode() if e.fp else ""
        print(f"ERR: HTTP {e.code} {e.reason} for {method} {path}\n{detail[:500]}",
              file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERR: cannot reach GlitchTip proxy at {BASE_URL}: {e.reason}",
              file=sys.stderr)
        sys.exit(1)


def _opt(args, name, default=None):
    """Pull '--name value' out of a positional arg list."""
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            val = args[i + 1]
            del args[i:i + 2]
            return val
        del args[i]
    return default


def _emit(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_list(args):
    project = _opt(args, "--project")
    query = _opt(args, "--query", "is:unresolved")
    limit = _opt(args, "--limit", "25")
    params = {"query": query, "limit": limit}
    if project:
        params["project"] = project
    qs = urllib.parse.urlencode(params)
    _emit(_request(f"/api/0/organizations/{ORG}/issues/?{qs}"))


def cmd_issue(args):
    if not args:
        print("issue: missing <issue-id>", file=sys.stderr)
        sys.exit(2)
    _emit(_request(f"/api/0/issues/{args[0]}/"))


def cmd_latest(args):
    if not args:
        print("latest: missing <issue-id>", file=sys.stderr)
        sys.exit(2)
    _emit(_request(f"/api/0/issues/{args[0]}/events/latest/"))


def cmd_events(args):
    limit = _opt(args, "--limit", "10")
    if not args:
        print("events: missing <issue-id>", file=sys.stderr)
        sys.exit(2)
    _emit(_request(f"/api/0/issues/{args[0]}/events/?limit={limit}"))


def cmd_resolve(args):
    if not args:
        print("resolve: missing <issue-id>", file=sys.stderr)
        sys.exit(2)
    _emit(_request(f"/api/0/issues/{args[0]}/", method="PUT",
                   body={"status": "resolved"}))


COMMANDS = {
    "list": cmd_list,
    "issue": cmd_issue,
    "latest": cmd_latest,
    "events": cmd_events,
    "resolve": cmd_resolve,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        sys.exit(0 if len(sys.argv) >= 2 else 1)
    command = sys.argv[1]
    handler = COMMANDS.get(command)
    if not handler:
        print(f"Unknown command: {command}\n\n{USAGE}", file=sys.stderr)
        sys.exit(2)
    handler(list(sys.argv[2:]))


if __name__ == "__main__":
    main()
