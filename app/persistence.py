from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import asyncpg

from .config import Config
from .filters import TS_FORMAT
from .store import CMDBRecord

LOGGER = logging.getLogger("cmdb-sim.persistence")


class CMDBPersistence:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        started = perf_counter()
        self._pool = await asyncpg.create_pool(
            host=self._cfg.db_host,
            port=self._cfg.db_port,
            user=self._cfg.db_user,
            password=self._cfg.db_password,
            database=self._cfg.db_name,
            min_size=1,
            max_size=10,
        )
        LOGGER.info("db_connect_complete duration_ms=%.2f", (perf_counter() - started) * 1000)
        await self._init_schema()
        LOGGER.info(
            "Postgres persistence enabled host=%s port=%s db=%s",
            self._cfg.db_host,
            self._cfg.db_port,
            self._cfg.db_name,
        )

    async def close(self) -> None:
        if self._pool is not None:
            started = perf_counter()
            await self._pool.close()
            LOGGER.info("db_pool_closed duration_ms=%.2f", (perf_counter() - started) * 1000)
            self._pool = None

    async def ensure_seed_data(self, generated: list[CMDBRecord]) -> None:
        pool = self._require_pool()
        started = perf_counter()
        async with pool.acquire() as conn:
            LOGGER.info("db_query_start sql=SELECT_COUNT_CMDB_RECORDS")
            current = await conn.fetchval("SELECT COUNT(*) FROM cmdb_records")
            LOGGER.info(
                "db_query_done sql=SELECT_COUNT_CMDB_RECORDS rows=1 duration_ms=%.2f",
                (perf_counter() - started) * 1000,
            )
            if int(current or 0) > 0:
                LOGGER.info("Found %s existing records in Postgres.", current)
                return

        await self._upsert_many(generated)
        LOGGER.info("Initialized Postgres with %d generated records.", len(generated))

    async def fetch_records(self, conditions: list[tuple[str, datetime]]) -> list[CMDBRecord]:
        where_sql = ""
        values: list[str] = []
        if conditions:
            clauses: list[str] = []
            op_map = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}
            for idx, (op, rhs) in enumerate(conditions, start=1):
                sql_op = op_map[op]
                clauses.append(f"sys_updated_on {sql_op} ${idx}")
                values.append(rhs.strftime(TS_FORMAT))
            where_sql = "WHERE " + " AND ".join(clauses)

        query = f"""
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
            {where_sql}
            ORDER BY sys_updated_on ASC
        """
        pool = self._require_pool()
        started = perf_counter()
        LOGGER.info(
            "db_query_start sql=SELECT_CMDB_RECORDS conditions=%d",
            len(conditions),
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)
        LOGGER.info(
            "db_query_done sql=SELECT_CMDB_RECORDS rows=%d duration_ms=%.2f",
            len(rows),
            (perf_counter() - started) * 1000,
        )
        return [self._row_to_record(row) for row in rows]

    async def mutate_random(
        self, requested: int, max_record_changes_per_hour: int
    ) -> int:
        if requested <= 0:
            return 0

        now_str = datetime.now(UTC).strftime(TS_FORMAT)
        pool = self._require_pool()
        started = perf_counter()
        LOGGER.info(
            "db_txn_start op=MUTATE_RANDOM requested=%d hourly_cap=%d",
            requested,
            max_record_changes_per_hour,
        )
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM cmdb_mutation_events
                    WHERE changed_at < (NOW() - INTERVAL '24 hours')
                    """
                )
                used = await conn.fetchval(
                    """
                    SELECT COALESCE(SUM(change_count), 0)
                    FROM cmdb_mutation_events
                    WHERE changed_at > (NOW() - INTERVAL '1 hour')
                    """
                )
                allowance = max(0, max_record_changes_per_hour - int(used or 0))
                mutate_count = min(requested, allowance)
                LOGGER.info(
                    "db_mutation_allowance used_last_hour=%d allowance=%d selected=%d",
                    int(used or 0),
                    allowance,
                    mutate_count,
                )
                if mutate_count <= 0:
                    LOGGER.info(
                        "db_txn_done op=MUTATE_RANDOM mutated=0 duration_ms=%.2f",
                        (perf_counter() - started) * 1000,
                    )
                    return 0

                rows = await conn.fetch(
                    """
                    WITH selected AS (
                        SELECT
                            sys_id,
                            sys_updated_on AS prev_updated_on,
                            u_segmentation_group_tag AS prev_seg_tag,
                            u_sync AS prev_u_sync,
                            sys_mod_count AS prev_mod_count
                        FROM cmdb_records
                        ORDER BY random()
                        LIMIT $1
                    ),
                    updated AS (
                        UPDATE cmdb_records c
                        SET
                            sys_updated_on = $2,
                            u_segmentation_group_tag = (
                                'cts:security-group-tag='
                                || (1000 + floor(random() * 9000))::int
                                || '-'
                                || lpad((floor(random() * 1000))::int::text, 3, '0')
                            ),
                            u_sync = CASE WHEN c.u_sync = 'false' THEN 'true' ELSE 'false' END,
                            sys_mod_count = ((c.sys_mod_count::int + (1 + floor(random() * 3))::int))::text
                        FROM selected s
                        WHERE c.sys_id = s.sys_id
                        RETURNING
                            c.sys_id,
                            s.prev_updated_on,
                            c.sys_updated_on,
                            s.prev_seg_tag,
                            c.u_segmentation_group_tag,
                            s.prev_u_sync,
                            c.u_sync,
                            s.prev_mod_count,
                            c.sys_mod_count
                    )
                    SELECT * FROM updated
                    """,
                    mutate_count,
                    now_str,
                )
                if rows:
                    await conn.execute(
                        """
                        INSERT INTO cmdb_mutation_events (change_count)
                        SELECT 1
                        FROM generate_series(1, $1)
                        """,
                        len(rows),
                    )

                for row in rows:
                    LOGGER.info(
                        "record_updated sys_id=%s sys_updated_on_old=%s sys_updated_on_new=%s "
                        "u_segmentation_group_tag_old=%s u_segmentation_group_tag_new=%s "
                        "u_sync_old=%s u_sync_new=%s sys_mod_count_old=%s sys_mod_count_new=%s",
                        row["sys_id"],
                        row["prev_updated_on"],
                        row["sys_updated_on"],
                        row["prev_seg_tag"],
                        row["u_segmentation_group_tag"],
                        row["prev_u_sync"],
                        row["u_sync"],
                        row["prev_mod_count"],
                        row["sys_mod_count"],
                    )

                LOGGER.info(
                    "db_txn_done op=MUTATE_RANDOM mutated=%d duration_ms=%.2f",
                    len(rows),
                    (perf_counter() - started) * 1000,
                )
                return len(rows)

    async def _upsert_many(self, records: list[CMDBRecord]) -> None:
        if not records:
            return
        payload = [self._record_to_params(record) for record in records]
        pool = self._require_pool()
        started = perf_counter()
        LOGGER.info("db_txn_start op=UPSERT_MANY rows=%d", len(records))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
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
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18
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
                    """,
                    payload,
                )
        LOGGER.info(
            "db_txn_done op=UPSERT_MANY rows=%d duration_ms=%.2f",
            len(records),
            (perf_counter() - started) * 1000,
        )

    async def _init_schema(self) -> None:
        pool = self._require_pool()
        started = perf_counter()
        LOGGER.info("db_txn_start op=INIT_SCHEMA")
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
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cmdb_mutation_events (
                    id BIGSERIAL PRIMARY KEY,
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    change_count INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        LOGGER.info(
            "db_txn_done op=INIT_SCHEMA duration_ms=%.2f",
            (perf_counter() - started) * 1000,
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
