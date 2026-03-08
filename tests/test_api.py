import pytest

from app.config import Config
from app.main import create_app


@pytest.fixture
def config() -> Config:
    return Config(
        host="127.0.0.1",
        port=8080,
        tls_enabled=False,
        tls_port=8443,
        tls_cert_file="/tmp/cert.pem",
        tls_key_file="/tmp/key.pem",
        tls_auto_generate=True,
        tls_keep_http_listener=True,
        cmdb_record_count=20,
        max_record_changes_per_hour=1000,
        mutation_tick_seconds=3600,
        max_mutations_per_tick=0,
        random_seed=123,
        mutation_enabled=False,
        persistence_enabled=False,
        db_host="localhost",
        db_port=5432,
        db_user="cmdb",
        db_password="cmdb",
        db_name="cmdb",
    )


@pytest.mark.asyncio
async def test_cmdb_sorted(app_client, config: Config) -> None:
    app = create_app(config)
    client = await app_client(app)

    resp = await client.get("/api/v1/cmdb")
    assert resp.status == 200
    payload = await resp.json()
    rows = payload["result"]
    values = [r["sys_updated_on"] for r in rows]
    assert values == sorted(values)


@pytest.mark.asyncio
async def test_cmdb_filter(app_client, config: Config) -> None:
    app = create_app(config)
    client = await app_client(app)

    resp = await client.get("/api/v1/cmdb?sys_updated_on.gte.2020-01-01+00:00:00")
    assert resp.status == 200

    payload = await resp.json()
    assert len(payload["result"]) > 0


@pytest.mark.asyncio
async def test_cmdb_filter_invalid(app_client, config: Config) -> None:
    app = create_app(config)
    client = await app_client(app)

    resp = await client.get("/api/v1/cmdb?sys_updated_on.nope.2020-01-01+00:00:00")
    assert resp.status == 400
