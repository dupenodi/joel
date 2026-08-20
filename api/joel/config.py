"""Environment-backed application configuration."""

from dataclasses import dataclass, replace
import os


def hydra_namespace_for(org_id: int) -> str:
    """Per-org Hydra graph namespace (Mode B tenant isolation)."""
    return f"joel-org-{org_id}"


@dataclass(frozen=True)
class Settings:
    """One universe: a single install, a single store dir, a single graph
    (§2.1). No dataset switch — that was a hackathon-era two-universe
    design the compose file never actually supported.

    Mode B: each org gets its own Hydra namespace via `for_org` / 
    `hydra_namespace_for`; the env default remains the install baseline.
    """

    hydra_http: str
    hydra_bolt: str
    hydra_token: str
    hydra_namespace: str
    hydra_cell: str
    embed_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            hydra_http=os.environ["HYDRA_HTTP"].rstrip("/"),
            hydra_bolt=os.environ["HYDRA_BOLT"],
            hydra_token=os.environ["HYDRA_TOKEN"],
            hydra_namespace=os.getenv("HYDRA_NAMESPACE", "default"),
            hydra_cell=os.getenv("HYDRA_CELL", "cell-0"),
            embed_model=os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        )

    def for_org(self, org_id: int) -> "Settings":
        """Settings with X-Graph-Namespace scoped to this org."""
        return replace(self, hydra_namespace=hydra_namespace_for(org_id))
