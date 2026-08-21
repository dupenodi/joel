"""Thin HTTP and Bolt client for HydraDB."""

from typing import Any

from neo4j import GraphDatabase
import requests

from .config import Settings


class Hydra:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.driver = GraphDatabase.driver(
            self.settings.hydra_bolt,
            auth=("neo4j", self.settings.hydra_token),
        )

    def close(self) -> None:
        self.driver.close()

    def __enter__(self) -> "Hydra":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def q(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        strong: bool = False,
    ) -> dict[str, Any]:
        """HTTP query endpoint.

        On the local build verified for Checkpoint 0/1, this endpoint does
        NOT bind `$param` values at all -- every parameterized query fails
        with "missing OpenCypher query parameter", even though the HTTP body
        carries `params` correctly. Use this only for the strong-consistency
        read-after-write checks (literal, agent-controlled values), and use
        `bolt()` for anything else -- especially anything containing
        document text, where string-interpolating into Cypher would be an
        injection risk as well as a correctness one.
        """
        body: dict[str, Any] = {
            "cell_id": self.settings.hydra_cell,
            "query": cypher,
        }
        if params:
            body["params"] = params
        if strong:
            body["consistency"] = "strong"

        response = requests.post(
            f"{self.settings.hydra_http}/v1/graphs/default/query",
            headers={
                "Authorization": f"Bearer {self.settings.hydra_token}",
                "X-Graph-Namespace": self.settings.hydra_namespace,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def bolt(self, cypher: str, **params: Any) -> list[Any]:
        """Bolt names the graph scope through the database name, which is how
        a workspace's writes stay out of every other workspace's graph. This
        used to be hardcoded to `"default"` while only the HTTP header carried
        the namespace — and since every write and nearly every read in this
        codebase goes over Bolt (see TRANSPORT in store.py), that meant the
        per-org namespace decided nothing at all: every workspace read and
        wrote the one root graph. Derive it from settings like the header."""
        with self.driver.session(database=self.settings.hydra_database) as session:
            return list(session.run(cypher, **params))
