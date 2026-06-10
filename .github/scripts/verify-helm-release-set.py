#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def release_key(release):
    return release["namespace"], release["name"]


def main():
    if len(sys.argv) != 3:
        print("usage: verify-helm-release-set.py DESIRED_JSON LIVE_JSON", file=sys.stderr)
        return 2

    desired = json.loads(Path(sys.argv[1]).read_text())
    live = json.loads(Path(sys.argv[2]).read_text())

    desired_set = {
        release_key(release)
        for release in desired
        if release.get("enabled") and release.get("installed")
    }
    live_set = {release_key(release) for release in live}

    extra = sorted(live_set - desired_set)
    missing = sorted(desired_set - live_set)
    unhealthy = sorted(
        (release["namespace"], release["name"], release.get("status", ""))
        for release in live
        if release_key(release) in desired_set and release.get("status") != "deployed"
    )

    if extra:
        print("Unexpected Helm releases not defined in helmfile:", file=sys.stderr)
        for namespace, name in extra:
            print(f"  - {namespace}/{name}", file=sys.stderr)

    if missing:
        print("Expected Helm releases missing from the cluster:", file=sys.stderr)
        for namespace, name in missing:
            print(f"  - {namespace}/{name}", file=sys.stderr)

    if unhealthy:
        print("Expected Helm releases not deployed:", file=sys.stderr)
        for namespace, name, status in unhealthy:
            print(f"  - {namespace}/{name}: {status}", file=sys.stderr)

    if extra or missing or unhealthy:
        return 1

    print("Live Helm release set matches helmfile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
