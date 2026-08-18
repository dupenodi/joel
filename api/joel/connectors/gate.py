"""Joel’s integration allowlist — not Composio’s full catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationDef:
    id: str
    toolkit: str
    name: str
    group: str
    connectable: bool
    ingest: bool
    scope: str
    default_lookback_days: int = 30
    default_interval_min: int = 15


INTEGRATIONS: tuple[IntegrationDef, ...] = (
    IntegrationDef(
        id="slack",
        toolkit="slack",
        name="Slack",
        group="chat",
        connectable=True,
        ingest=True,
        scope="Channels you pick, plus threads. No DMs.",
        default_interval_min=15,
    ),
    IntegrationDef(
        id="github",
        toolkit="github",
        name="GitHub",
        group="code",
        connectable=True,
        ingest=True,
        scope="Issues, PRs, review comments, and language-aware code chunks.",
        default_interval_min=30,
    ),
    IntegrationDef(
        id="gmail",
        toolkit="gmail",
        name="Gmail",
        group="mail",
        connectable=True,
        ingest=True,
        scope="Mail threads you’re authorized for.",
        default_interval_min=20,
    ),
    IntegrationDef(
        id="linear",
        toolkit="linear",
        name="Linear",
        group="tracker",
        connectable=True,
        ingest=True,
        scope="Issues and comments.",
        default_interval_min=30,
    ),
    IntegrationDef(
        id="jira",
        toolkit="jira",
        name="Jira",
        group="tracker",
        connectable=True,
        ingest=True,
        scope="Issues and comments.",
        default_interval_min=30,
    ),
    IntegrationDef(
        id="notion",
        toolkit="notion",
        name="Notion",
        group="docs",
        connectable=True,
        ingest=True,
        scope="Pages you’re authorized for.",
        default_interval_min=60,
    ),
    IntegrationDef(
        id="confluence",
        toolkit="confluence",
        name="Confluence",
        group="docs",
        connectable=True,
        ingest=True,
        scope="Spaces and pages you’re authorized for.",
        default_interval_min=60,
    ),
    IntegrationDef(
        id="googledrive",
        toolkit="googledrive",
        name="Google Drive",
        group="docs",
        connectable=True,
        ingest=True,
        scope="Docs, text files, and PDFs you’re authorized for.",
        default_interval_min=60,
    ),
    IntegrationDef(
        id="hubspot",
        toolkit="hubspot",
        name="HubSpot",
        group="crm",
        connectable=True,
        ingest=True,
        scope="Deals in pipelines you’re authorized for.",
        default_interval_min=60,
    ),
    IntegrationDef(
        id="fireflies",
        toolkit="fireflies",
        name="Fireflies",
        group="meetings",
        connectable=True,
        ingest=True,
        scope="Meeting transcripts.",
        default_interval_min=60,
    ),
)

INTEGRATION_BY_ID = {item.id: item for item in INTEGRATIONS}
INTEGRATION_BY_TOOLKIT = {item.toolkit: item for item in INTEGRATIONS}
CONNECTABLE_TOOLKITS = {item.toolkit for item in INTEGRATIONS if item.connectable}
INGEST_PROVIDERS = {item.id for item in INTEGRATIONS if item.ingest}

GROUP_LABELS = {
    "chat": "Chat",
    "code": "Code",
    "mail": "Mail",
    "tracker": "Trackers",
    "docs": "Docs",
    "crm": "CRM",
    "meetings": "Meetings",
}

LOOKBACK_DAYS = (7, 30, 90, 365)


def require_connectable(toolkit: str) -> IntegrationDef:
    slug = toolkit.strip().lower()
    item = INTEGRATION_BY_TOOLKIT.get(slug)
    if item is None or not item.connectable:
        allowed = ", ".join(sorted(CONNECTABLE_TOOLKITS))
        raise ValueError(f"Toolkit “{toolkit}” isn’t on Joel’s list. Connectable: {allowed}.")
    return item
