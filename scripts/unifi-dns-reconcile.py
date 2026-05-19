#!/usr/bin/env python3
"""Reconcile UniFi static DNS records against per-site YAML files.

YAML under --records-root is the full state — anything in UniFi but not in
YAML is deleted. See --help for commands.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RECORDS_ROOT = "turner-services-sensitive-repo/unifi-dns"
V2_DNS_PATH = "/proxy/network/v2/api/site/{slug}/static-dns"
INTEGRATION_SITES_PATH = "/proxy/network/integration/v1/sites"
INTEGRATION_DNS_PATH = "/proxy/network/integration/v1/sites/{site_id}/dns/policies"

MASK_ENABLED = False
_MASKED: set[str] = set()


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def mask(*values: str | None) -> None:
    if not MASK_ENABLED:
        return
    for v in values:
        if not v:
            continue
        s = str(v).strip()
        if s and s not in _MASKED:
            print(f"::add-mask::{s}", flush=True)
            _MASKED.add(s)


def make_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def api_call(
    method: str,
    url: str,
    api_key: str,
    body: dict | None = None,
    swallow_codes: set[int] | None = None,
) -> Any:
    data = None
    # integration v1 rejects mixed-case "X-API-Key" with 401; v2 accepts either.
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, context=make_ssl_ctx()) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if swallow_codes and e.code in swallow_codes:
            return None
        body_text = e.read().decode("utf-8", "replace")
        die(f"{method} {url} -> HTTP {e.code}: {body_text}")
    except urllib.error.URLError as e:
        die(f"{method} {url} failed: {e.reason}")


def normalize_record(rec: dict) -> dict:
    return {
        "name": rec.get("key") or rec.get("name"),
        "type": (rec.get("record_type") or rec.get("type") or "A").upper(),
        "value": rec.get("value"),
        "enabled": rec.get("enabled", True),
    }


def to_v2_payload(rec: dict) -> dict:
    return {
        "key": rec["name"],
        "record_type": rec["type"],
        "value": rec["value"],
        "enabled": bool(rec.get("enabled", True)),
    }


def record_key(rec: dict) -> tuple[str, str]:
    return (rec["name"].lower(), rec["type"].upper())


def load_consoles(root: Path) -> dict[str, dict]:
    cfg = root / "consoles.yml"
    if not cfg.exists():
        die(f"missing {cfg}")
    doc = yaml.safe_load(cfg.read_text()) or {}
    consoles = doc.get("consoles") or {}
    if not consoles:
        die(f"{cfg}: no consoles defined")
    for name, c in consoles.items():
        if not c.get("url"):
            die(f"console {name}: missing url")
        if not c.get("api_key_env"):
            die(f"console {name}: missing api_key_env")
        c.setdefault("api_version", "auto")
    return consoles


def load_site_records(path: Path) -> list[dict]:
    doc = yaml.safe_load(path.read_text()) or {}
    raw_records = doc.get("records") or []
    if not isinstance(raw_records, list):
        die(f"{path}: records must be a list")
    out = []
    seen: set[tuple[str, str]] = set()
    for r in raw_records:
        if not r.get("name") or not r.get("value"):
            die(f"{path}: record missing name/value: {r}")
        norm = normalize_record(r)
        k = record_key(norm)
        if k in seen:
            die(f"{path}: duplicate record {norm['name']} {norm['type']}")
        seen.add(k)
        out.append(norm)
    return out


def discover_site_files(root: Path, console: str) -> list[tuple[str, Path]]:
    dir_ = root / console
    if not dir_.is_dir():
        return []
    out = []
    for p in sorted(dir_.glob("*.yml")):
        if p.name.startswith("_"):
            continue
        doc = yaml.safe_load(p.read_text()) or {}
        slug = doc.get("site") or p.stem
        out.append((slug, p))
    return out


def get_api_key(console_name: str, console: dict) -> str:
    env_var = console["api_key_env"]
    key = os.environ.get(env_var)
    if not key:
        die(f"console {console_name}: env var {env_var} not set")
    return key


def list_integration_sites(controller_url: str, api_key: str) -> list[dict] | None:
    # 401/403/404 all mean "this endpoint isn't usable" — let callers fall back to v2.
    url = controller_url.rstrip("/") + INTEGRATION_SITES_PATH
    raw = api_call("GET", url, api_key, swallow_codes={401, 403, 404})
    if raw is None:
        return None
    if isinstance(raw, dict) and "data" in raw:
        return raw["data"]
    if isinstance(raw, list):
        return raw
    die(f"unexpected /sites response: {type(raw).__name__}")


def resolve_api_version(console: dict, controller_url: str, api_key: str) -> str:
    requested = console.get("api_version", "auto")
    if requested in ("v2", "integration"):
        return requested
    # integration v1 DNS writes are not yet wired; always land on v2 until a 10.1 controller pins the schema.
    return "v2"


def fetch_v2(controller_url: str, slug: str, api_key: str) -> list[dict]:
    url = controller_url.rstrip("/") + V2_DNS_PATH.format(slug=slug)
    raw = api_call("GET", url, api_key)
    if raw is None:
        return []
    items = raw["data"] if isinstance(raw, dict) and "data" in raw else raw
    out = []
    for item in items:
        norm = normalize_record(item)
        norm["_id"] = item.get("_id")
        out.append(norm)
    return out


def apply_v2(
    controller_url: str,
    slug: str,
    api_key: str,
    to_create: list[dict],
    to_update: list[tuple[dict, dict]],
    to_delete: list[dict],
) -> None:
    base = controller_url.rstrip("/") + V2_DNS_PATH.format(slug=slug)
    for r in to_create:
        mask(r["name"], r["value"])
        api_call("POST", base, api_key, to_v2_payload(r))
        print(f"    created: {r['type']} {r['name']} -> {r['value']}")
    for have, want in to_update:
        mask(want["name"], want["value"])
        url = f"{base}/{have['_id']}"
        payload = to_v2_payload(want)
        payload["_id"] = have["_id"]
        api_call("PUT", url, api_key, payload)
        print(f"    updated: {want['type']} {want['name']} -> {want['value']}")
    for r in to_delete:
        mask(r["name"], r["value"])
        url = f"{base}/{r['_id']}"
        api_call("DELETE", url, api_key)
        print(f"    deleted: {r['type']} {r['name']} -> {r['value']}")


def diff(
    desired: list[dict], current: list[dict]
) -> tuple[list[dict], list[tuple[dict, dict]], list[dict]]:
    cur_by_key = {record_key(r): r for r in current}
    des_by_key = {record_key(r): r for r in desired}
    to_create = [r for k, r in des_by_key.items() if k not in cur_by_key]
    to_update: list[tuple[dict, dict]] = []
    for k, want in des_by_key.items():
        have = cur_by_key.get(k)
        if have is None:
            continue
        if have["value"] != want["value"] or bool(have.get("enabled", True)) != bool(
            want.get("enabled", True)
        ):
            to_update.append((have, want))
    to_delete = [r for k, r in cur_by_key.items() if k not in des_by_key]
    return to_create, to_update, to_delete


def print_plan(
    label: str,
    to_create: list[dict],
    to_update: list[tuple[dict, dict]],
    to_delete: list[dict],
) -> None:
    # Emit masks before any record print so the GHA scrubber catches them.
    for r in to_create + to_delete:
        mask(r["name"], r["value"])
    for have, want in to_update:
        mask(want["name"], want["value"], have["value"])
    if not (to_create or to_update or to_delete):
        print(f"  {label}: no changes")
        return
    print(f"  {label}: +{len(to_create)} ~{len(to_update)} -{len(to_delete)}")
    for r in to_create:
        print(f"    + {r['type']:5s} {r['name']} -> {r['value']}")
    for have, want in to_update:
        print(f"    ~ {want['type']:5s} {want['name']}: {have['value']} -> {want['value']}")
    for r in to_delete:
        print(f"    - {r['type']:5s} {r['name']} -> {r['value']}")


def export_yaml(records: list[dict]) -> str:
    cleaned = [
        {k: v for k, v in r.items() if k != "_id"}
        for r in sorted(records, key=record_key)
    ]
    return yaml.safe_dump({"records": cleaned}, sort_keys=False, default_flow_style=False)


def cmd_list_consoles(consoles: dict[str, dict]) -> int:
    for name, c in consoles.items():
        mask(c["url"])
        print(f"{name}\t{c['url']}\t{c['api_key_env']}\t{c['api_version']}")
    return 0


def cmd_list_sites(consoles: dict[str, dict], filter_console: str | None) -> int:
    rc = 0
    for name, c in consoles.items():
        if filter_console and name != filter_console:
            continue
        mask(c["url"])
        print(f"console: {name} ({c['url']})")
        api_key = get_api_key(name, c)
        sites = list_integration_sites(c["url"], api_key)
        if sites is None:
            print("  /sites endpoint returned 404 — controller too old for v1 discovery")
            rc = 1
            continue
        for s in sites:
            slug = s.get("internalReference") or s.get("name") or "?"
            uuid = s.get("id") or "?"
            display = s.get("description") or s.get("name") or ""
            mask(slug, uuid, display)
            print(f"  {slug}\t{uuid}\t{display}")
    return rc


def cmd_export(consoles: dict[str, dict], target: str) -> int:
    if "/" not in target:
        die(f"--export expects <console>/<site>, got {target!r}")
    console_name, slug = target.split("/", 1)
    if console_name not in consoles:
        die(f"unknown console {console_name!r}")
    c = consoles[console_name]
    api_key = get_api_key(console_name, c)
    current = fetch_v2(c["url"], slug, api_key)
    sys.stdout.write(export_yaml(current))
    return 0


def cmd_reconcile(
    root: Path,
    consoles: dict[str, dict],
    filter_console: str | None,
    check_only: bool,
) -> int:
    any_changes = False
    rc = 0
    for name, c in consoles.items():
        if filter_console and name != filter_console:
            continue
        mask(c["url"])
        print(f"console: {name} ({c['url']})")
        sites = discover_site_files(root, name)
        if not sites:
            print("  (no site files)")
            continue
        api_key = get_api_key(name, c)
        api_version = resolve_api_version(c, c["url"], api_key)
        if api_version != "v2":
            print(f"  warning: api_version={api_version} not yet implemented for writes; using v2")
            api_version = "v2"
        for slug, path in sites:
            label = f"site {slug} ({path.name})"
            try:
                desired = load_site_records(path)
                current = fetch_v2(c["url"], slug, api_key)
                to_create, to_update, to_delete = diff(desired, current)
                print_plan(label, to_create, to_update, to_delete)
                if to_create or to_update or to_delete:
                    any_changes = True
                    if not check_only:
                        apply_v2(c["url"], slug, api_key, to_create, to_update, to_delete)
            except SystemExit:
                raise
            except Exception as e:
                print(f"  {label}: FAILED — {e}")
                rc = 1
    if check_only and any_changes:
        print("(--check) plan shown; no changes applied")
    return rc


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--records-root",
        default=os.environ.get("UNIFI_DNS_RECORDS_ROOT", DEFAULT_RECORDS_ROOT),
        help=f"Path to records root (default: {DEFAULT_RECORDS_ROOT})",
    )
    p.add_argument("--console", default=None, help="Restrict to one console")
    p.add_argument("--check", action="store_true", help="Plan only; no writes")
    p.add_argument(
        "--mask-output",
        action="store_true",
        help="Emit GitHub Actions ::add-mask:: directives for record names, "
        "values, controller URLs, and site identifiers (auto-on when "
        "GITHUB_ACTIONS=true).",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--list-consoles", action="store_true")
    g.add_argument("--list-sites", action="store_true")
    g.add_argument("--export", metavar="CONSOLE/SITE", default=None)
    args = p.parse_args()

    # --export emits raw YAML; masking would corrupt it.
    global MASK_ENABLED
    MASK_ENABLED = not args.export and (
        args.mask_output or os.environ.get("GITHUB_ACTIONS") == "true"
    )

    root = Path(args.records_root)
    consoles = load_consoles(root)

    if args.console and args.console not in consoles:
        die(f"unknown console {args.console!r}; configured: {', '.join(consoles)}")

    if args.list_consoles:
        return cmd_list_consoles(consoles)
    if args.list_sites:
        return cmd_list_sites(consoles, args.console)
    if args.export:
        return cmd_export(consoles, args.export)
    return cmd_reconcile(root, consoles, args.console, args.check)


if __name__ == "__main__":
    sys.exit(main())
