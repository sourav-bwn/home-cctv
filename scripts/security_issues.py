"""Create a GitHub issue for each new Semgrep finding, without duplicate issues.

Runs only after a successful scanner step. Uses only Python's standard library.
"""
import json
import os
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

API = "https://api.github.com"
MARKER = "<!-- semgrep-finding:"


def request(method, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(API + path, data=body, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    try:
        # URL is fixed to api.github.com with a GitHub-owned repository path.
        with urlopen(req, timeout=20) as response:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            return json.load(response)
    except HTTPError as exc:
        print(f"GitHub API {method} {path} returned HTTP {exc.code}", file=sys.stderr)
        raise


def marker_for(finding):
    # Anonymous Semgrep CE may omit a fingerprint ("requires login").
    # Use rule, path and line as a deterministic fallback; moves may yield a new issue.
    fingerprint = finding.get("extra", {}).get("fingerprint")
    if not fingerprint or fingerprint == "requires login":
        fingerprint = str(finding["start"]["line"])
    from hashlib import sha256
    raw = "\0".join((finding["check_id"], finding["path"], fingerprint))
    return MARKER + sha256(raw.encode()).hexdigest() + " -->"


def existing_markers(repo):
    known = set()
    for page in range(1, 101):
        issues = request("GET", f"/repos/{repo}/issues?state=all&per_page=100&page={page}")
        for issue in issues:
            if "pull_request" in issue:
                continue
            body = issue.get("body") or ""
            for line in body.splitlines():
                if line.startswith(MARKER) and line.endswith(" -->"):
                    known.add(line)
        if len(issues) < 100:
            return known
    raise RuntimeError("More than 10,000 issues; refusing incomplete deduplication")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: security_issues.py findings.json")
    with open(sys.argv[1], encoding="utf-8") as source:
        data = json.load(source)
    if data.get("errors"):
        raise RuntimeError("Scan reported errors; not creating partial findings")
    findings = data["results"]
    if not isinstance(findings, list):
        raise ValueError("Invalid Semgrep results")
    repo = os.environ["GITHUB_REPOSITORY"]
    if not repo.startswith("sourav-bwn/"):
        raise ValueError("Refusing to post outside the owner's repositories")
    known = existing_markers(repo) if findings else set()
    created = 0
    for finding in findings:
        marker = marker_for(finding)
        if marker in known:
            continue
        rule = finding["check_id"]
        path = finding["path"]
        line = finding["start"]["line"]
        message = finding.get("extra", {}).get("message", "Review the flagged code.")
        severity = finding.get("extra", {}).get("severity", "UNKNOWN")
        title = f"Security scan: {rule} in {path}"
        # Avoid posting source snippets or secrets; findings are static-analysis leads.
        title = " ".join(title.split())[:240]
        run_url = f"https://github.com/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        file_url = (f"https://github.com/{repo}/blob/{os.environ['GITHUB_SHA']}/"
                    f"{quote(path, safe='/')}#L{line}")
        body = (f"{marker}\n\nSemgrep CE flagged a possible security issue. "
                "This is not proof of an exploitable vulnerability; review before changing code.\n\n"
                f"- Rule: `{rule}`\n- Severity: `{severity}`\n- Location: {file_url}\n"
                f"- Scanner message: {message[:1000]}\n- Scan: {run_url}\n\n"
                "If this is a false positive, close this issue; the scanner won't reopen it.\n")
        issue = request("POST", f"/repos/{repo}/issues", {"title": title, "body": body})
        print("Created:", issue["html_url"])
        known.add(marker)
        created += 1
    print(f"{len(findings)} findings, {created} new issues")


if __name__ == "__main__":
    main()
