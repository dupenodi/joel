"""Environment-backed application configuration."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    dataset: str
    hydra_http: str
    hydra_bolt: str
    hydra_token: str
    hydra_namespace: str
    hydra_cell: str
    embed_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        dataset = os.getenv("JOEL_DATASET", "main")
        if dataset not in {"main", "bench"}:
            raise ValueError("JOEL_DATASET must be 'main' or 'bench'")

        return cls(
            dataset=dataset,
            hydra_http=os.environ["HYDRA_HTTP"].rstrip("/"),
            hydra_bolt=os.environ["HYDRA_BOLT"],
            hydra_token=os.environ["HYDRA_TOKEN"],
            hydra_namespace=os.getenv("HYDRA_NAMESPACE", "default"),
            hydra_cell=os.getenv("HYDRA_CELL", "cell-0"),
            embed_model=os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        )
