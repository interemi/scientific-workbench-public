#!/usr/bin/env python3
"""Inventory publication privacy and possible secrets without printing matched values."""

import argparse
from collections import defaultdict
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 5 * 1024 * 1024
SECRET_RULES = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "provider_token": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{24,}|xai-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{24,})\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._-]{24,}\b", re.I),
    "unquoted_provider_assignment": re.compile(
        r'''\b(?:OPENAI_API_KEY|XAI_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY)\s*=\s*[A-Za-z0-9][A-Za-z0-9_./-]{15,}(?=$|[\s;"'])'''),
    "credential_assignment": re.compile(
        r'''\b(?:OPENAI_API_KEY|XAI_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|api_key|apiKey|password|access_token)\b["']?\s*[:=]\s*["']([A-Za-z0-9._/-]{16,})["']'''),
}
PRIVACY_RULES = {
    "user_directory": re.compile(r"/Users/[^/\s\"'`]+"),
    "email_address": re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b"),
}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def fingerprint(line):
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def load_fixtures(root):
    path = root / "distribution/publication-secret-fixtures.json"
    if not path.exists():
        return set()
    document = json.loads(path.read_text())
    if document.get("schema_version") != 1:
        raise ValueError("unsupported reviewed-fixture schema")
    result = set()
    for entry in document["entries"]:
        if (entry["rule"] not in SECRET_RULES or not entry.get("reason")
                or not re.fullmatch(r"[a-f0-9]{64}", entry["line_sha256"])):
            raise ValueError("invalid reviewed-fixture entry")
        result.add((entry["path"], entry["rule"], entry["line_sha256"]))
    return result


def scan_text(data, paths, identity, fixtures):
    pending, reviewed, privacy = [], [], []
    text = data.decode("utf-8", errors="replace")
    for number, line in enumerate(text.splitlines(), 1):
        digest = fingerprint(line)
        for rule, pattern in SECRET_RULES.items():
            if pattern.search(line):
                for path in sorted(paths):
                    finding = {"path": path, "object": identity, "line": number,
                               "rule": rule, "line_sha256": digest}
                    (reviewed if (path, rule, digest) in fixtures else pending).append(finding)
        for rule, pattern in PRIVACY_RULES.items():
            if pattern.search(line):
                privacy.append({"paths": sorted(paths), "object": identity, "line": number,
                                "rule": rule, "line_sha256": digest})
    return pending, reviewed, privacy


def audit(root=ROOT, history=False):
    fixtures = load_fixtures(root)
    try:
        head = git(root, "rev-parse", "--verify", "HEAD").decode().strip()
    except subprocess.CalledProcessError:
        head = None
    report = {"schema_version": 1, "mode": "reachable_history" if history else "git_candidates",
              "head": head,
              "potential_secrets": [], "reviewed_fixture_matches": [], "privacy_findings": [],
              "binary_objects": [], "oversized_objects": [], "objects_scanned": 0,
              "limits": ["Pattern-based triage, not proof that no secret exists.",
                         "No matched values are included in this report.",
                         "Binary contents require separate metadata/text review.",
                         "Unreachable Git objects and ignored local files are not publication candidates."]}
    if history:
        if git(root, "rev-parse", "--is-shallow-repository").strip() == b"true":
            raise ValueError("history audit requires a full clone; shallow history is incomplete")
        commits = git(root, "rev-list", "--all").decode().splitlines()
        report["commits"] = commits
        objects = defaultdict(set)
        for commit in commits:
            for entry in git(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
                if entry:
                    header, path = entry.split(b"\t", 1)
                    mode, kind, oid = header.decode().split()
                    if kind == "blob":
                        objects[oid].add(path.decode("utf-8", errors="surrogateescape"))
        sources = itertools.chain(
            ((oid, paths, git(root, "cat-file", "blob", oid)) for oid, paths in sorted(objects.items())),
            ((f"commit:{commit}", {"(commit metadata)"}, git(root, "cat-file", "commit", commit)) for commit in commits),
        )
        report["limits"].append("Annotated tag metadata is not scanned; review it separately before tagging a release.")
        signatures = set(git(root, "log", "--all", "--format=%ae%n%ce").decode().splitlines())
        report["commit_email_metadata"] = [{
            "sha256": fingerprint(address),
            "kind": "github_noreply" if address.endswith("users.noreply.github.com") else
                    "local_address" if address.endswith(".local") else "other_address",
        } for address in sorted(signatures) if address]
    else:
        paths = set(filter(None, git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")))

        def candidates():
            for relative in sorted(paths):
                path = root / relative
                if path.is_symlink():
                    data = os.readlink(path).encode()
                elif path.is_file():
                    if not path.resolve().is_relative_to(root.resolve()):
                        raise ValueError("candidate resolves outside the checkout")
                    data = path.read_bytes()
                else:
                    continue
                yield hashlib.sha256(data).hexdigest(), {relative}, data
        sources = candidates()
    for identity, paths, data in sources:
        if len(data) > MAX_TEXT_BYTES:
            report["oversized_objects"].append({"object": identity, "paths": sorted(paths), "bytes": len(data)})
            continue
        if b"\0" in data or data.startswith((b"%PDF", b"\x89PNG", b"SIMPLE  =", b"icns")):
            report["binary_objects"].append({"object": identity, "paths": sorted(paths), "bytes": len(data)})
            continue
        pending, reviewed, privacy = scan_text(data, paths, identity, fixtures)
        report["potential_secrets"].extend(pending)
        report["reviewed_fixture_matches"].extend(reviewed)
        report["privacy_findings"].extend(privacy)
        report["objects_scanned"] += 1
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="scan every blob in all reachable local refs")
    parser.add_argument("--check-secrets", action="store_true", help="fail for unreviewed secret matches or oversized objects")
    parser.add_argument("--output", type=Path, help="new report outside the checkout; existing reports are preserved")
    args = parser.parse_args(argv)
    if args.output and args.output.expanduser().resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("keep audit evidence outside the source checkout")
    report = audit(history=args.history)
    if args.output:
        output = args.output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
    print(json.dumps({"mode": report["mode"], "objects_scanned": report["objects_scanned"],
                      "potential_secrets": len(report["potential_secrets"]),
                      "reviewed_fixture_matches": len(report["reviewed_fixture_matches"]),
                      "privacy_findings": len(report["privacy_findings"]),
                      "binary_objects": len(report["binary_objects"]),
                      "oversized_objects": len(report["oversized_objects"])}))
    return int(args.check_secrets and bool(report["potential_secrets"] or report["oversized_objects"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Publication audit stopped: {error.__class__.__name__}; inspect inputs and Git access.")
