import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from attackpath.api.main import create_app
from attackpath.config import Settings


def test_health_is_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_when_database_is_available(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["database"] is True


def test_ready_is_503_when_database_is_unreachable() -> None:
    settings = Settings(
        app_env="ci",
        database_url="postgresql://127.0.0.1:1/unused",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] is False


def test_ready_is_503_when_database_is_down(client: TestClient, db_state) -> None:
    db_state["up"] = False
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] is False
    db_state["up"] = True


def test_list_documents_paginates(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"limit": 2})
    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_search_filters_records(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"q": "beta"})

    assert [record["id"] for record in response.json()["items"]] == ["002"]


def test_get_document_found(client: TestClient) -> None:
    response = client.get("/v1/documents/001")

    assert response.status_code == 200
    assert response.json()["title"] == "Alpha guideline"


def test_missing_document_is_problem_details(client: TestClient) -> None:
    response = client.get("/v1/documents/999")
    body = response.json()

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["detail"] == "No document with id '999'."
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_bad_limit_is_422_problem(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"limit": 0})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["errors"][0]["field"] == "query.limit"


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"


def test_bad_filter_name_is_400_problem(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"Bad-Name": "1"})

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert "Invalid filter name" in response.json()["detail"]


def test_offset_is_applied(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"limit": 1, "offset": 2})

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "003"


def test_no_search_results(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"q": "not-present"})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_metadata_filter(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"year": "2024"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["002"]
    assert response.json()["filters"] == {"year": "2024"}


def test_sort_title(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"sort": "-title"})

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "003"


def test_invalid_sort_is_400(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"sort": "name"})

    assert response.status_code == 400
    assert "Invalid sort" in response.json()["detail"]


def test_limit_above_max_is_422(client: TestClient) -> None:
    response = client.get("/v1/documents", params={"limit": 101})

    assert response.status_code == 422


def test_app_refuses_to_start_without_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_app_rejects_invalid_app_env() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="prod", _env_file=None)
