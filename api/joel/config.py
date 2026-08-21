"""Environment-backed application configuration."""

import base64
from dataclasses import dataclass, replace
import os

# HydraDB's scoped-database naming, from `HierarchicalClientDatabaseResolver`:
# a Bolt database of `{base}.{VERSION}.{tenant}.{sub_tenant}` resolves to the
# namespace path `{root}/{tenant}[/{sub_tenant}]`, where each id segment is
# URL-safe unpadded base64. `_` means "no sub-tenant". The HTTP transport
# addresses the identical scope by sending that namespace path in
# `X-Graph-Namespace`, so the two transports must be derived together or they
# silently read different graphs.
_SCOPE_VERSION = "scope1"
_NO_SUB_TENANT = "_"


def org_tenant_id(org_id: int) -> str:
    """The tenant identity a workspace occupies inside the install's graph."""
    return f"joel-org-{org_id}"


def _scope_segment(tenant_id: str) -> str:
    return base64.urlsafe_b64encode(tenant_id.encode("utf-8")).decode("ascii").rstrip("=")


def hydra_namespace_for(org_id: int, *, root: str = "default") -> str:
    """`X-Graph-Namespace` path for one workspace: the install root, then the
    workspace's tenant segment."""
    return f"{root}/{_scope_segment(org_tenant_id(org_id))}"


def hydra_database_for(org_id: int, *, base: str = "default") -> str:
    """Bolt database name addressing the same scope as `hydra_namespace_for`."""
    segment = _scope_segment(org_tenant_id(org_id))
    return f"{base}.{_SCOPE_VERSION}.{segment}.{_NO_SUB_TENANT}"


@dataclass(frozen=True)
class Settings:
    """One universe: a single install, a single store dir, a single graph
    (§2.1). No dataset switch — that was a hackathon-era two-universe
    design the compose file never actually supported.

    Tenancy is HydraDB's, not ours. `for_org` pins these settings to one
    workspace's graph scope; every read and write then lands in a store the
    server keeps separate, rather than in a shared graph we would have to
    remember to filter. `hydra_org is None` addresses the install root — the
    pre-tenancy graph, which `scripts/migrate_graph_scope.py` moves into a
    workspace scope.
    """

    hydra_http: str
    hydra_bolt: str
    hydra_token: str
    hydra_root_namespace: str
    hydra_base_database: str
    hydra_cell: str
    embed_model: str
    hydra_org: int | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            hydra_http=os.environ["HYDRA_HTTP"].rstrip("/"),
            hydra_bolt=os.environ["HYDRA_BOLT"],
            hydra_token=os.environ["HYDRA_TOKEN"],
            hydra_root_namespace=os.getenv("HYDRA_NAMESPACE", "default"),
            hydra_base_database=os.getenv("HYDRA_DATABASE", "default"),
            hydra_cell=os.getenv("HYDRA_CELL", "cell-0"),
            embed_model=os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        )

    @property
    def hydra_namespace(self) -> str:
        """The namespace path this Settings addresses, for HTTP."""
        if self.hydra_org is None:
            return self.hydra_root_namespace
        return hydra_namespace_for(self.hydra_org, root=self.hydra_root_namespace)

    @property
    def hydra_database(self) -> str:
        """The Bolt database naming that same scope."""
        if self.hydra_org is None:
            return self.hydra_base_database
        return hydra_database_for(self.hydra_org, base=self.hydra_base_database)

    def for_org(self, org_id: int) -> "Settings":
        """Settings pinned to one workspace's graph scope. Idempotent: the
        scope is derived from `hydra_org` on read, never accumulated into the
        stored name, so `s.for_org(1).for_org(2)` addresses org 2 rather than
        a nested tenant that does not exist."""
        return replace(self, hydra_org=org_id)
