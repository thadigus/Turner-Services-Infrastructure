from __future__ import annotations

import json
import os
import ssl
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import pulumi
from pulumi import dynamic


class ProxmoxHAApiError(RuntimeError):
    pass


def _bool_param(value: Any) -> str:
    return "1" if bool(value) else "0"


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _nodes_param(nodes: Dict[str, int]) -> List[str]:
    return [f"{node}:{int(priority)}" for node, priority in nodes.items()]


def _api_token_header() -> str:
    username = os.environ.get("PROXMOX_VE_USERNAME")
    token = os.environ.get("PROXMOX_VE_API_TOKEN")
    if not username or not token:
        raise ProxmoxHAApiError("Missing PROXMOX_VE_USERNAME/PROXMOX_VE_API_TOKEN for HA API management")
    return f"PVEAPIToken={username}={token}"


def _request(props: Dict[str, Any], method: str, path: str, data: Optional[Dict[str, Any]] = None) -> Any:
    endpoint = str(props["endpoint"]).rstrip("/")
    payload = None
    headers = {"Authorization": _api_token_header()}
    if data is not None:
        cleaned = {key: value for key, value in data.items() if value is not None}
        payload = urlencode(cleaned, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(
        f"{endpoint}/api2/json{path}",
        data=payload,
        headers=headers,
        method=method,
    )
    context = ssl._create_unverified_context() if props.get("insecure", True) else None
    try:
        with urlopen(request, context=context, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        missing = "no such resource" in detail or "no such ha rule" in detail
        if error.code == 404 or (method in {"GET", "DELETE"} and missing):
            return None
        raise ProxmoxHAApiError(f"Proxmox API {method} {path} failed with HTTP {error.code}: {detail}") from error
    if not body:
        return None
    parsed = json.loads(body)
    return parsed.get("data")


def _resource_path(resource_id: str) -> str:
    return f"/cluster/ha/resources/{quote(resource_id, safe='')}"


def _rule_path(rule_name: str) -> str:
    return f"/cluster/ha/rules/{quote(rule_name, safe='')}"


def _resource_payload(props: Dict[str, Any], include_sid: bool) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "state": props.get("state"),
        "comment": props.get("comment"),
        "max_restart": _optional_int(props.get("max_restart")),
        "max_relocate": _optional_int(props.get("max_relocate")),
        "failback": _bool_param(props.get("failback", False)),
        "auto-rebalance": _bool_param(props.get("auto_rebalance", True)),
    }
    if include_sid:
        payload["sid"] = props["resource_id"]
        payload["type"] = props.get("resource_type")
    else:
        payload["delete"] = "group"
    return payload


def _rule_payload(props: Dict[str, Any], include_rule: bool) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "type": "node-affinity",
        "resources": props["resource_id"],
        "nodes": _nodes_param(props["nodes"]),
        "strict": _bool_param(props.get("strict", True)),
        "disable": _bool_param(props.get("disabled", False)),
        "comment": props.get("rule_comment") or props.get("comment"),
    }
    if include_rule:
        payload["rule"] = props["rule_name"]
    return payload


def _ensure_policy(props: Dict[str, Any]) -> None:
    resource_id = props["resource_id"]
    rule_name = props["rule_name"]

    existing_resource = _request(props, "GET", _resource_path(resource_id))
    if existing_resource is None:
        _request(props, "POST", "/cluster/ha/resources", _resource_payload(props, include_sid=True))
    else:
        _request(props, "PUT", _resource_path(resource_id), _resource_payload(props, include_sid=False))

    existing_rule = _request(props, "GET", _rule_path(rule_name))
    if existing_rule is None:
        _request(props, "POST", "/cluster/ha/rules", _rule_payload(props, include_rule=True))
    else:
        _request(props, "PUT", _rule_path(rule_name), _rule_payload(props, include_rule=False))


def _delete_policy(props: Dict[str, Any]) -> None:
    rule_name = props.get("rule_name")
    resource_id = props.get("resource_id")
    if rule_name:
        _request(props, "DELETE", _rule_path(rule_name))
    if resource_id:
        _request(props, "DELETE", _resource_path(resource_id), {"purge": "1"})


class ProxmoxHANodeAffinityProvider(dynamic.ResourceProvider):
    def check(self, olds: Dict[str, Any], news: Dict[str, Any]) -> dynamic.CheckResult:
        return dynamic.CheckResult(inputs=news, failures=[])

    def diff(self, id: str, olds: Dict[str, Any], news: Dict[str, Any]) -> dynamic.DiffResult:
        comparable_old = {key: olds.get(key) for key in news}
        return dynamic.DiffResult(changes=comparable_old != news)

    def create(self, props: Dict[str, Any]) -> dynamic.CreateResult:
        _ensure_policy(props)
        return dynamic.CreateResult(id_=props["resource_id"], outs=props)

    def update(self, id: str, olds: Dict[str, Any], news: Dict[str, Any]) -> dynamic.UpdateResult:
        _ensure_policy(news)
        if olds.get("rule_name") and olds.get("rule_name") != news.get("rule_name"):
            _request(olds, "DELETE", _rule_path(olds["rule_name"]))
        return dynamic.UpdateResult(outs=news)

    def delete(self, id: str, props: Dict[str, Any]) -> None:
        _delete_policy(props)


class ProxmoxHANodeAffinityPolicy(dynamic.Resource):
    def __init__(
        self,
        name: str,
        endpoint: str,
        insecure: bool,
        resource_id: str,
        resource_type: str,
        state: str,
        max_restart: Optional[int],
        max_relocate: Optional[int],
        comment: Optional[str],
        rule_name: str,
        nodes: Dict[str, int],
        strict: bool,
        failback: bool,
        opts: Optional[pulumi.ResourceOptions] = None,
    ) -> None:
        super().__init__(
            ProxmoxHANodeAffinityProvider(),
            name,
            {
                "endpoint": endpoint,
                "insecure": insecure,
                "resource_id": resource_id,
                "resource_type": resource_type,
                "state": state,
                "max_restart": max_restart,
                "max_relocate": max_relocate,
                "comment": comment,
                "rule_name": rule_name,
                "rule_comment": comment,
                "nodes": nodes,
                "strict": strict,
                "failback": failback,
                "auto_rebalance": True,
                "disabled": False,
            },
            opts,
        )
