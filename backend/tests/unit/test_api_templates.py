import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.main import app

client = TestClient(app)


from app.models.template import Template


def test_list_templates(mocker):
    mock_db = mocker.AsyncMock()

    class MockResult:
        def scalars(self):
            class MockAll:
                def all(self):
                    template_mock = Template(
                        slug="fantasy",
                        name="Fantasy",
                        description="Desc",
                        difficulty=3,
                        tags=["fantasy"],
                    )
                    return [template_mock]

            return MockAll()

    mock_db.execute.return_value = MockResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get("/api/templates")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["slug"] == "fantasy"

    app.dependency_overrides.clear()


def test_get_template(mocker):
    mock_db = mocker.AsyncMock()

    class MockResult:
        def scalar_one_or_none(self):
            return Template(
                slug="fantasy",
                name="Fantasy",
                description="Desc",
                author="John",
                version="1.0",
                difficulty=3,
                tags=["fantasy"],
                content={"key": "value"},
            )

    mock_db.execute.return_value = MockResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get("/api/templates/fantasy")
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "fantasy"
    assert data["content"]["key"] == "value"

    app.dependency_overrides.clear()


def test_get_template_not_found(mocker):
    mock_db = mocker.AsyncMock()

    class MockResult:
        def scalar_one_or_none(self):
            return None

    mock_db.execute.return_value = MockResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get("/api/templates/nonexistent")
    assert response.status_code == 404

    app.dependency_overrides.clear()
