"""Chat conversation basics: list, create, get, rename, delete, isolation."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

import joel.app as app  # noqa: E402
from joel import identity  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


def _setup_client(tmp: Path) -> TestClient:
    app.DATA_DIR = tmp
    app.DB_PATH = tmp / "index" / "joel.db"
    app.init_db()
    client = TestClient(app.app)
    res = client.post(
        "/api/auth/setup",
        json={
            "email": "ada@acme.test",
            "password": "secretsecret",
            "display_name": "Ada",
            "domain": "acme.test",
        },
    )
    assert res.status_code == 200, res.text
    return client


def _add_message(conversation_id: str, created_at: str, content: str) -> None:
    with app.db() as conn:
        conn.execute(
            """INSERT INTO messages(id, conversation_id, role, content_json, created_at)
               VALUES (?,?,?,?,?)""",
            (
                f"m_{conversation_id}_{created_at}",
                conversation_id,
                "user",
                json.dumps({"role": "user", "content": content}),
                created_at,
            ),
        )


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ada = _setup_client(tmp)

        bare = TestClient(app.app)
        assert bare.get("/api/conversations").status_code == 401
        assert bare.delete("/api/conversations/c_nope").status_code == 401

        created = ada.post(
            "/api/conversations", json={"title": "Older thread"}
        ).json()
        newer = ada.post("/api/conversations", json={"title": "Newer thread"}).json()
        assert created["id"].startswith("c_")
        assert created["updated_at"] == created["created_at"]

        listed = ada.get("/api/conversations").json()
        assert [c["id"] for c in listed] == [newer["id"], created["id"]]

        _add_message(created["id"], "2026-08-21T12:00:00+00:00", "bump")
        listed = ada.get("/api/conversations").json()
        assert [c["id"] for c in listed] == [created["id"], newer["id"]]
        assert listed[0]["updated_at"] == "2026-08-21T12:00:00+00:00"

        got = ada.get(f"/api/conversations/{created['id']}").json()
        assert got["title"] == "Older thread"
        assert len(got["messages"]) == 1
        assert got["messages"][0]["content"] == "bump"

        renamed = ada.patch(
            f"/api/conversations/{created['id']}",
            json={"title": "  Renamed thread  "},
        ).json()
        assert renamed["title"] == "Renamed thread"
        assert ada.patch(
            f"/api/conversations/{created['id']}", json={"title": "   "}
        ).status_code == 400

        gone = ada.delete(f"/api/conversations/{created['id']}")
        assert gone.status_code == 200
        assert gone.json() == {"status": "deleted"}
        assert ada.get(f"/api/conversations/{created['id']}").status_code == 404
        with app.db() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE conversation_id=?",
                (created["id"],),
            ).fetchone()["n"]
            assert n == 0
        leftover = ada.get("/api/conversations").json()
        assert [c["id"] for c in leftover] == [newer["id"]]
        assert ada.delete(f"/api/conversations/{created['id']}").status_code == 404

        with app.db() as conn:
            actor = identity.actor_from_session(
                conn, ada.cookies.get("joel_session")
            )
            assert actor is not None
            _invite_id, token = identity.create_invite(
                conn, actor, email="sam@acme.test", role="member"
            )
            identity.accept_invite(
                conn, token, password="secretsecret", display_name="Sam"
            )

        sam = TestClient(app.app)
        login = sam.post(
            "/api/auth/login",
            json={"email": "sam@acme.test", "password": "secretsecret"},
        )
        assert login.status_code == 200, login.text
        assert sam.get(f"/api/conversations/{newer['id']}").status_code == 404
        assert sam.patch(
            f"/api/conversations/{newer['id']}", json={"title": "stolen"}
        ).status_code == 404
        assert sam.delete(f"/api/conversations/{newer['id']}").status_code == 404
        assert sam.get("/api/conversations").json() == []
        still = ada.get(f"/api/conversations/{newer['id']}").json()
        assert still["title"] == "Newer thread"

        print("ok  conversations: list recency, rename, delete, isolation")


if __name__ == "__main__":
    main()
