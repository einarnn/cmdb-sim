from __future__ import annotations

import logging
from typing import Any

import asyncpg

from .config import Config
from .store import CMDBRecord

LOGGER = logging.getLogger("cmdb-sim.persistence")


UPSERT_SQL = """
INSERT INTO cmdb_records (
    sys_id,
    u_account_name,
    u_macaddress,
    u_processed,
    u_segmentation_group_tag,
    sys_mod_count,
    u_hostname,
    sys_updated_on,
    sys_tags,
    u_community_group,
    u_config_item,
    u_sync,
    sys_updated_by,
    u_id,
    sys_created_on,
    u_ci_status,
    u_host_name,
    sys_created_by
)
VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
)
ON CONFLICT (sys_id) DO UPDATE SET
    u_account_name = EXCLUDED.u_account_name,
    u_macaddress = EXCLUDED.u_macaddress,
    u_processed = EXCLUDED.u_processed,
    u_segmentation_group_tag = EXCLUDED.u_segmentation_group_tag,
    sys_mod_count = EXCLUDED.sys_mod_count,
    u_hostname = EXCLUDED.u_hostname,
    sys_updated_on = EXCLUDED.sys_updated_on,
    sys_tags = EXCLUDED.sys_tags,
    u_community_group = EXCLUDED.u_community_group,
    u_config_item = EXCLUDED.u_config_item,
    u_sync = EXCLUDED.u_sync,
    sys_updated_by = EXCLUDED.sys_updated_by,
    u_id = EXCLUDED.u_id,
    sys_created_on = EXCLUDED.sys_created_on,
    u_ci_status = EXCLUDED.u_ci_status,
    u_host_name = EXCLUDED.u_host_name,
    sys_created_by = EXCLUDED.sys_created_by
"""


class CMDBPersistence:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            host=self._cfg.db_host,
            port=self._cfg.db_port,
            user=self._cfg.db_user,
            password=self._cfg.db_password,
            database=self._cfg.db_name,
            min_size=1,
            max_size=5,
        )
        await self._init_schema()
        LOGGER.info(
            "Postgres persistence enabled host=%s port=%s db=%s",
            self._cfg.db_host,
            self._cfg.db_port,
            self._cfg.db_name,
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def bootstrap_records(self, generated: list[CMDBRecord]) -> list[CMDBRecord]:
        rows = await self.fetch_all()
        if rows:
            LOGGER.info("Loaded %d records from Postgres.", len(rows))
            return rows

        await self.upsert_many(generated)
        LOGGER.info("Initialized Postgres with %d generated records.", len(generated))
        return generated

    async def fetch_all(self) -> list[CMDBRecord]:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    u_account_name,
                    u_macaddress,
                    u_processed,
                    u_segmentation_group_tag,
                    sys_mod_count,
                    u_hostname,
                    sys_updated_on,
                    sys_tags,
                    u_community_group,
                    sys_id,
                    u_config_item,
                    u_sync,
                    sys_updated_by,
                    u_id,
                    sys_created_on,
                    u_ci_status,
                    u_host_name,
                    sys_created_by
                FROM cmdb_records
                ORDER BY sys_updated_on ASC
                """
            )
        return [self._row_to_record(row) for row in rows]

    async def upsert_many(self, records: list[CMDBRecord]) -> None:
        if not records:
            return
        payload = [self._record_to_params(record) for record in records]
        pool = self._require_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(UPSERT_SQL, payload)

    async def _init_schema(self) -> None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cmdb_records (
                    sys_id TEXT PRIMARY KEY,
                    u_account_name TEXT NOT NULL,
                    u_macaddress TEXT NOT NULL,
                    u_processed TEXT NOT NULL,
                    u_segmentation_group_tag TEXT NOT NULL,
                    sys_mod_count TEXT NOT NULL,
                    u_hostname TEXT NOT NULL,
                    sys_updated_on TEXT NOT NULL,
                    sys_tags TEXT NOT NULL,
                    u_community_group TEXT NOT NULL,
                    u_config_item TEXT NOT NULL,
                    u_sync TEXT NOT NULL,
                    sys_updated_by TEXT NOT NULL,
                    u_id TEXT NOT NULL,
                    sys_created_on TEXT NOT NULL,
                    u_ci_status TEXT NOT NULL,
                    u_host_name TEXT NOT NULL,
                    sys_created_by TEXT NOT NULL
                )
                """
            )

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Persistence pool is not initialized")
        return self._pool

    @staticmethod
    def _record_to_params(record: CMDBRecord) -> tuple[str, ...]:
        return (
            record["sys_id"],
            record["u_account_name"],
            record["u_macaddress"],
            record["u_processed"],
            record["u_segmentation_group_tag"],
            record["sys_mod_count"],
            record["u_hostname"],
            record["sys_updated_on"],
            record["sys_tags"],
            record["u_community_group"],
            record["u_config_item"],
            record["u_sync"],
            record["sys_updated_by"],
            record["u_id"],
            record["sys_created_on"],
            record["u_ci_status"],
            record["u_host_name"],
            record["sys_created_by"],
        )

    @staticmethod
    def _row_to_record(row: Any) -> CMDBRecord:
        return CMDBRecord(
            u_account_name=row["u_account_name"],
            u_macaddress=row["u_macaddress"],
            u_processed=row["u_processed"],
            u_segmentation_group_tag=row["u_segmentation_group_tag"],
            sys_mod_count=row["sys_mod_count"],
            u_hostname=row["u_hostname"],
            sys_updated_on=row["sys_updated_on"],
            sys_tags=row["sys_tags"],
            u_community_group=row["u_community_group"],
            sys_id=row["sys_id"],
            u_config_item=row["u_config_item"],
            u_sync=row["u_sync"],
            sys_updated_by=row["sys_updated_by"],
            u_id=row["u_id"],
            sys_created_on=row["sys_created_on"],
            u_ci_status=row["u_ci_status"],
            u_host_name=row["u_host_name"],
            sys_created_by=row["sys_created_by"],
        )

