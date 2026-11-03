"""Tests run with APP_ENV=test (in-memory SQLite, .env ignored).

Swap any dependency with the container:

    def test_x(app):
        app.container.order_repository.override(FakeOrderRepository())
"""
import os

os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture
def app():
    from main import create_app

    application = create_app()
    yield application
    application.container.unwire()
    application.container.reset_override()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
