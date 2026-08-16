"""Verify the complete Phase 0 development environment."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import uuid

from dotenv import load_dotenv
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from joel.config import Settings  # noqa: E402
from joel.hydra import Hydra  # noqa: E402


def check_hydra_smoke() -> None:
    hydra_repo = Path(
        os.getenv("HYDRA_REPO", ROOT.parent / "hydradb")
    ).expanduser()
    if not (hydra_repo / "justfile").is_file():
        raise RuntimeError(f"HydraDB checkout not found at {hydra_repo}")

    subprocess.run(["just", "smoke"], cwd=hydra_repo, check=True)


def check_hydra_protocols(settings: Settings) -> None:
    marker = uuid.uuid4().int % 1_000_000_000

    with Hydra(settings) as hydra:
        hydra.q(
            f"CREATE (a {{id: {marker}}})-[:FOLLOWS]->"
            f"(b {{id: {marker + 1}}})"
        )
        result = hydra.q(
            f"MATCH (a {{id: {marker}}})-[:FOLLOWS]->(b) "
            "RETURN b.id AS id",
            strong=True,
        )
        rows = result.get("rows", [])
        if len(rows) != 1:
            raise AssertionError(f"HTTP round-trip returned {len(rows)} rows")

        value = rows[0][0]
        if isinstance(value, dict):
            value = value.get("value")
        if value != marker + 1:
            raise AssertionError(f"HTTP round-trip returned {value!r}")

        bolt_rows = hydra.bolt(
            f"MATCH (a {{id: {marker}}})-[:FOLLOWS]->(b) "
            "RETURN b.id AS id"
        )
        if len(bolt_rows) != 1 or bolt_rows[0]["id"] != marker + 1:
            raise AssertionError("Bolt edge read failed")


def check_llm_aliases() -> None:
    base_url = os.environ["LLM_BASE_URL"].rstrip("/")
    api_key = os.environ["LLM_API_KEY"]
    if not api_key:
        raise RuntimeError("LLM_API_KEY is required for Checkpoint 0")

    aliases = (
        "LLM_MODEL_DISTILL",
        "LLM_MODEL_EXTRACT",
        "LLM_MODEL_ANSWER",
        "LLM_MODEL_RESOLVE",
        "LLM_MODEL_RERANK",
    )
    for alias in aliases:
        model = os.environ[alias]
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 8,
                "temperature": 0,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("choices"):
            raise AssertionError(f"{alias} ({model}) returned no choices")


def check_embedding(settings: Settings) -> None:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.embed_model)
    embedding = model.encode(
        ["joel remembers company decisions"],
        normalize_embeddings=True,
    )
    if embedding.shape[0] != 1 or embedding.shape[1] <= 0:
        raise AssertionError(f"Unexpected embedding shape: {embedding.shape}")


def main() -> None:
    load_dotenv(ROOT / ".env")
    settings = Settings.from_env()

    checks = (
        ("HydraDB storage smoke", check_hydra_smoke),
        ("HydraDB HTTP and Bolt", lambda: check_hydra_protocols(settings)),
        ("LLM model aliases", check_llm_aliases),
        ("local embedding model", lambda: check_embedding(settings)),
    )
    for name, check in checks:
        print(f"checking {name}...", flush=True)
        check()
        print(f"ok: {name}", flush=True)

    print("Checkpoint 0 passed.")


if __name__ == "__main__":
    main()
