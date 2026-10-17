"""Narrow process-local proxy adjustments for known development endpoints."""

from __future__ import annotations

import os
import urllib.request
from collections.abc import MutableMapping, Sequence
from urllib.parse import urlsplit


def bypass_known_local_port_nine_proxy(
    hosts: Sequence[str], environment: MutableMapping[str, str] | None = None
) -> bool:
    """Add explicit host exclusions only when the configured proxy is loopback port 9."""

    env = environment if environment is not None else os.environ
    proxies = urllib.request.getproxies()
    https_proxy = proxies.get("https") or proxies.get("all")
    if not https_proxy:
        return False
    try:
        parsed = urlsplit(https_proxy if "://" in https_proxy else f"//{https_proxy}")
        port = parsed.port
    except ValueError:
        return False
    if (parsed.hostname or "").casefold() not in {"127.0.0.1", "localhost", "::1"}:
        return False
    if port != 9:
        return False
    existing = [
        part.strip()
        for key in ("NO_PROXY", "no_proxy")
        for part in env.get(key, "").split(",")
        if part.strip()
    ]
    normalized = {part.casefold() for part in existing}
    existing.extend(host for host in hosts if host.casefold() not in normalized)
    for key in ("NO_PROXY", "no_proxy"):
        env[key] = ",".join(existing)
    return True
