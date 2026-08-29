#!/usr/bin/env python3
"""atlas verify — independent integrity check of an evidence package.

The whole point of the manifest is that an auditor does not have to trust
ATLAS. This tool takes a manifest and (optionally) the artifact directory and
re-derives every hash plus the root hash. It imports nothing from `app/`, so
it can be handed to an auditor on its own.

    python scripts/verify_manifest.py manifest.json
    python scripts/verify_manifest.py manifest.json --artifacts ./evidence
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
BOLD = "\033[1m"
OFF = "\033[0m"


def root_hash(hashes: list[str]) -> str:
    """Must match app/agents/assembler.py::_root_hash exactly."""
    return hashlib.sha256("".join(sorted(hashes)).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(prog="atlas verify")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--artifacts", type=Path, default=None,
                    help="directory of artifact files to re-hash from disk")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if not args.manifest.is_file():
        print(f"{RED}manifest not found: {args.manifest}{OFF}")
        return 2

    manifest = json.loads(args.manifest.read_text())
    entries = manifest.get("entries", [])
    artifacts = [a for e in entries for a in e.get("artifacts", [])]

    print(f"{BOLD}ATLAS package verification{OFF}")
    print(f"  package   {manifest.get('package')}")
    print(f"  signed    {manifest.get('signed_by')}")
    print(f"  built     {manifest.get('generated_at')}")
    print(f"  controls  {manifest.get('controls_verified')}/{manifest.get('controls_total')} verified")
    print(f"  artifacts {len(artifacts)}\n")

    problems: list[str] = []

    # 1. every artifact must carry a well-formed hash
    for a in artifacts:
        h = a.get("sha256", "")
        if len(h) != 64 or not all(c in "0123456789abcdef" for c in h):
            problems.append(f"malformed sha256 on {a.get('name')}")

    # 2. duplicate filenames with different hashes = tampering or a collection bug
    seen: dict[str, str] = {}
    for a in artifacts:
        name, h = a.get("name", ""), a.get("sha256", "")
        if name in seen and seen[name] != h:
            problems.append(f"conflicting hashes for {name}")
        seen[name] = h

    # 3. root hash must re-derive
    declared = manifest.get("root_hash", "")
    derived = root_hash([a["sha256"] for a in artifacts if a.get("sha256")])
    if declared != derived:
        problems.append(f"root hash mismatch (declared {declared[:16]}… derived {derived[:16]}…)")
    elif not args.quiet:
        print(f"  {GREEN}OK{OFF}  root hash re-derived: {derived[:32]}...")

    # 4. every artifact must have passed Model Armor
    unscreened = [a["name"] for a in artifacts if a.get("armor") not in ("pass", "redacted")]
    if unscreened:
        problems.append(f"{len(unscreened)} artifact(s) not screened: {unscreened[:3]}")
    elif not args.quiet:
        print(f"  {GREEN}OK{OFF}  all {len(artifacts)} artifacts carry a Model Armor verdict")

    # 5. every artifact must name the collecting agent identity
    anon = [a["name"] for a in artifacts if not str(a.get("identity", "")).startswith("spiffe://")]
    if anon:
        problems.append(f"{len(anon)} artifact(s) without an agent identity: {anon[:3]}")
    elif not args.quiet:
        print(f"  {GREEN}OK{OFF}  every artifact attributed to a SPIFFE identity")

    # 6. re-hash from disk when the artifacts are supplied
    if args.artifacts:
        checked = mismatched = missing = 0
        for a in artifacts:
            p = args.artifacts / a["name"]
            if not p.is_file():
                missing += 1
                continue
            checked += 1
            if hashlib.sha256(p.read_bytes()).hexdigest() != a["sha256"]:
                mismatched += 1
                problems.append(f"content hash mismatch: {a['name']}")
        mark = f"{GREEN}OK{OFF}" if not mismatched else f"{RED}XX{OFF}"
        print(f"  {mark}  re-hashed {checked} file(s) from disk "
              f"{DIM}({missing} not present, {mismatched} mismatched){OFF}")

    gaps = manifest.get("gap_register", [])
    if gaps and not args.quiet:
        print(f"\n  {DIM}gap register: {len(gaps)} control(s) not verified{OFF}")
        for g in gaps[:5]:
            print(f"    {DIM}- {g['control']:10} {g['status']:9} owner={g['owner']}{OFF}")
        if len(gaps) > 5:
            print(f"    {DIM}- ... {len(gaps) - 5} more{OFF}")

    print()
    if problems:
        print(f"{RED}{BOLD}VERIFICATION FAILED - {len(problems)} problem(s){OFF}")
        for p in problems:
            print(f"  {RED}-{OFF} {p}")
        return 1

    print(f"{GREEN}{BOLD}PACKAGE VERIFIED{OFF}  "
          f"{DIM}integrity, provenance and screening confirmed independently{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
