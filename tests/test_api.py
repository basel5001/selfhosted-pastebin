"""Tests for the pastebin API."""

import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

# Use a temporary database for tests
_tmp = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_PATH"] = _tmp

from src.main import app, _rate_store  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_db():
    """Reset the database and rate limiter before each test."""
    from src.database import get_connection, init_db

    _rate_store.clear()
    init_db()
    yield
    # Clean up
    with get_connection() as conn:
        conn.execute("DELETE FROM pastes")
        conn.commit()


@pytest.fixture
def client():
    return TestClient(app)


def _create_paste(client, **overrides):
    """Helper to create a paste and return the response."""
    payload = {
        "content": "SGVsbG8gV29ybGQ=",  # base64 "Hello World" (simulating encrypted)
        "language": "plain",
        "expires_in": "1d",
        **overrides,
    }
    return client.post("/api/paste", json=payload)


# ---- Create paste ----


class TestCreatePaste:
    def test_create_paste_success(self, client):
        res = _create_paste(client)
        assert res.status_code == 201
        data = res.json()
        assert "id" in data
        assert "url" in data
        assert len(data["id"]) == 8

    def test_create_paste_empty_content(self, client):
        res = _create_paste(client, content="")
        assert res.status_code == 400

    def test_create_paste_too_large(self, client):
        big = "A" * (512 * 1024 + 1)
        res = _create_paste(client, content=big)
        assert res.status_code == 413

    def test_create_paste_invalid_expiry(self, client):
        res = _create_paste(client, expires_in="2y")
        assert res.status_code == 400

    def test_create_paste_with_language(self, client):
        res = _create_paste(client, language="python")
        assert res.status_code == 201
        paste_id = res.json()["id"]
        get_res = client.get(f"/api/paste/{paste_id}")
        assert get_res.json()["language"] == "python"


# ---- Read paste ----


class TestReadPaste:
    def test_read_paste(self, client):
        create_res = _create_paste(client)
        paste_id = create_res.json()["id"]
        res = client.get(f"/api/paste/{paste_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["content"] == "SGVsbG8gV29ybGQ="
        assert data["views"] == 1

    def test_read_paste_increments_views(self, client):
        create_res = _create_paste(client)
        paste_id = create_res.json()["id"]
        client.get(f"/api/paste/{paste_id}")
        res = client.get(f"/api/paste/{paste_id}")
        assert res.json()["views"] == 2

    def test_read_paste_not_found(self, client):
        res = client.get("/api/paste/nonexist")
        assert res.status_code == 404


# ---- Expired paste ----


class TestExpiredPaste:
    def test_expired_paste_returns_404(self, client):
        res = _create_paste(client, expires_in="1h")
        paste_id = res.json()["id"]

        # Manually expire it in the database
        from src.database import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE pastes SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                (paste_id,),
            )
            conn.commit()

        get_res = client.get(f"/api/paste/{paste_id}")
        assert get_res.status_code == 404

    def test_never_expire(self, client):
        res = _create_paste(client, expires_in="never")
        paste_id = res.json()["id"]
        get_res = client.get(f"/api/paste/{paste_id}")
        assert get_res.status_code == 200
        assert get_res.json()["expires_at"] is None


# ---- Password-protected paste ----


class TestPasswordProtected:
    def test_password_required(self, client):
        res = _create_paste(client, password="secret123")
        paste_id = res.json()["id"]
        get_res = client.get(f"/api/paste/{paste_id}")
        assert get_res.status_code == 401

    def test_wrong_password(self, client):
        res = _create_paste(client, password="secret123")
        paste_id = res.json()["id"]
        get_res = client.get(f"/api/paste/{paste_id}?password=wrong")
        assert get_res.status_code == 403

    def test_correct_password(self, client):
        res = _create_paste(client, password="secret123")
        paste_id = res.json()["id"]
        get_res = client.get(f"/api/paste/{paste_id}?password=secret123")
        assert get_res.status_code == 200
        assert get_res.json()["content"] == "SGVsbG8gV29ybGQ="


# ---- Burn after read ----


class TestBurnAfterRead:
    def test_burn_deletes_after_read(self, client):
        res = _create_paste(client, burn_after_read=True)
        paste_id = res.json()["id"]

        # First read succeeds
        first = client.get(f"/api/paste/{paste_id}")
        assert first.status_code == 200
        assert first.json()["burn_after_read"] is True

        # Second read should 404
        second = client.get(f"/api/paste/{paste_id}")
        assert second.status_code == 404


# ---- Rate limiting ----


class TestRateLimit:
    def test_rate_limit_enforced(self, client):
        # Create 10 pastes (the limit)
        for _ in range(10):
            res = _create_paste(client)
            assert res.status_code == 201

        # The 11th should be rate-limited
        res = _create_paste(client)
        assert res.status_code == 429


# ---- Delete paste ----


class TestDeletePaste:
    def test_delete_paste(self, client):
        create_res = _create_paste(client)
        paste_id = create_res.json()["id"]
        del_res = client.delete(f"/api/paste/{paste_id}")
        assert del_res.status_code == 200
        get_res = client.get(f"/api/paste/{paste_id}")
        assert get_res.status_code == 404

    def test_delete_nonexistent(self, client):
        res = client.delete("/api/paste/nonexist")
        assert res.status_code == 404


# ---- Health check ----


class TestHealth:
    def test_health_endpoint(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


# ---- Index page ----


class TestPages:
    def test_index_page(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "pastebin" in res.text.lower()

    def test_view_page_existing_paste(self, client):
        create_res = _create_paste(client)
        paste_id = create_res.json()["id"]
        res = client.get(f"/{paste_id}")
        assert res.status_code == 200

    def test_view_page_nonexistent(self, client):
        res = client.get("/nonexist")
        assert res.status_code == 404
