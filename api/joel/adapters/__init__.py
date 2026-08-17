"""Source adapters — raw provider payloads → CanonicalDoc via manifests."""

from joel.adapters.base import (
    SourceManifest,
    TriageReport,
    adapt,
    adapt_many,
    group_threads,
    triage,
    triage_batch,
)
from joel.adapters.manifests import (
    GITHUB_ISSUE,
    GITHUB_ISSUE_COMMENT,
    GITHUB_PR,
    GMAIL,
    SLACK,
)

__all__ = [
    "SourceManifest",
    "TriageReport",
    "adapt",
    "adapt_many",
    "group_threads",
    "triage",
    "triage_batch",
    "SLACK",
    "GITHUB_ISSUE",
    "GITHUB_ISSUE_COMMENT",
    "GITHUB_PR",
    "GMAIL",
]
