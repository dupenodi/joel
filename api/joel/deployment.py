"""Cloud vs self-host.

Callers ask `deployment()` / `slack_install()` — they do not parse env
themselves. Same seam later for hosted-only product flavor (billing, …):
add a function here, don't scatter origin checks. MCP OAuth is not
hosted-only — this origin is the authorization server in both modes.

Detection (Outline-style):

1. `JOEL_DEPLOYMENT=cloud|selfhost` wins (local cloud testing, staging).
2. Else `JOEL_WEB_ORIGIN` host is `meetjoel.xyz` or a subdomain → cloud.
3. Else self-host.

Slack install is a *capability*, not the same bit:

- env has Slack app credentials → Add to Slack (OAuth)
- cloud without those credentials → unavailable (never teach customers
  to create a Slack app)
- self-host without those credentials → manifest + paste (today)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse
import os

DeploymentMode = Literal["cloud", "selfhost"]
SlackInstall = Literal["oauth", "manifest", "unavailable"]

HOSTED_ROOT_DOMAIN = "meetjoel.xyz"


def _host(origin: str) -> str:
    raw = (origin or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return (parsed.hostname or "").lower().rstrip(".")


def host_is_hosted(host: str) -> bool:
    """True for meetjoel.xyz and any subdomain (app., www., staging.)."""
    name = (host or "").lower().rstrip(".")
    return name == HOSTED_ROOT_DOMAIN or name.endswith("." + HOSTED_ROOT_DOMAIN)


@dataclass(frozen=True)
class Deployment:
    mode: DeploymentMode
    web_origin: str

    @property
    def is_cloud(self) -> bool:
        return self.mode == "cloud"


def web_origin() -> str:
    return os.getenv("JOEL_WEB_ORIGIN", "http://localhost:3000").rstrip("/")


def from_env() -> Deployment:
    origin = web_origin()
    explicit = os.getenv("JOEL_DEPLOYMENT", "").strip().lower().replace("-", "")
    if explicit in {"cloud", "hosted"}:
        mode: DeploymentMode = "cloud"
    elif explicit in {"selfhost", "selfhosted", "oss"}:
        mode = "selfhost"
    else:
        mode = "cloud" if host_is_hosted(_host(origin)) else "selfhost"
    return Deployment(mode=mode, web_origin=origin)


def deployment() -> Deployment:
    return from_env()


def slack_client_id() -> str:
    return os.getenv("SLACK_CLIENT_ID", "").strip()


def slack_client_secret() -> str:
    return os.getenv("SLACK_CLIENT_SECRET", "").strip()


def slack_signing_secret() -> str:
    """Signing secret for the *hosted* Slack app (one app, every customer).

    Self-host manifest installs keep their secret in org settings instead.
    """
    return os.getenv("SLACK_SIGNING_SECRET", "").strip()


def slack_oauth_configured() -> bool:
    return bool(slack_client_id() and slack_client_secret() and slack_signing_secret())


def slack_install() -> SlackInstall:
    if slack_oauth_configured():
        return "oauth"
    if deployment().is_cloud:
        return "unavailable"
    return "manifest"


__all__ = [
    "HOSTED_ROOT_DOMAIN",
    "Deployment",
    "DeploymentMode",
    "SlackInstall",
    "deployment",
    "from_env",
    "host_is_hosted",
    "slack_client_id",
    "slack_client_secret",
    "slack_install",
    "slack_oauth_configured",
    "slack_signing_secret",
    "web_origin",
]
