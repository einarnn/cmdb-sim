from pathlib import Path
import sys

import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

# Ensure "app" package imports work even when pytest is launched outside repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest_asyncio.fixture
async def app_client():
    clients: list[TestClient] = []

    async def factory(app):
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        clients.append(client)
        return client

    try:
        yield factory
    finally:
        while clients:
            await clients.pop().close()
