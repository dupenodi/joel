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
        with self.driver.session(database="default") as session:
            return list(session.run(cypher, **params))
