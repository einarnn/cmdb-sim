from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from .filters import TS_FORMAT

LOGGER = logging.getLogger("cmdb-sim.store")


class CMDBRecord(TypedDict):
    u_account_name: str
    u_macaddress: str
    u_processed: str
    u_segmentation_group_tag: str
    sys_mod_count: str
    u_hostname: str
    sys_updated_on: str
    sys_tags: str
    u_community_group: str
    sys_id: str
    u_config_item: str
    u_sync: str
    sys_updated_by: str
    u_id: str
    sys_created_on: str
    u_ci_status: str
    u_host_name: str
    sys_created_by: str


def _ts(value: datetime) -> str:
    return value.strftime(TS_FORMAT)


def generate_records(count: int, seed: int = 42) -> list[CMDBRecord]:
    rng = random.Random(seed)
    now = datetime.now(UTC).replace(tzinfo=None)
    records: list[CMDBRecord] = []
    for idx in range(1, count + 1):
        acct = f"W{idx:05d}"
        created = now - timedelta(days=rng.randint(1, 365), seconds=rng.randint(0, 86399))
        hostname = f"Test_{idx}"
        sys_id = f"{idx:032x}"[-32:]
        mac = ":".join(f"{rng.randint(0, 255):02x}" for _ in range(6))
        records.append(
            CMDBRecord(
                u_account_name=acct,
                u_macaddress=mac,
                u_processed=_ts(created),
                u_segmentation_group_tag=f"cts:security-group-tag={rng.randint(1000,9999)}-{rng.randint(0,999):03d}",
                sys_mod_count="0",
                u_hostname=hostname,
                sys_updated_on=_ts(created),
                sys_tags="",
                u_community_group="Administration",
                sys_id=sys_id,
                u_config_item=f"SNtoDataMart{idx}",
                u_sync="false",
                sys_updated_by="DGS06_admin",
                u_id="",
                sys_created_on=_ts(created),
                u_ci_status="Operational",
                u_host_name=hostname,
                sys_created_by="DGS06_admin",
            )
        )
    return records


class CMDBStore:
    def __init__(self, records: list[CMDBRecord], max_record_changes_per_hour: int, seed: int):
        self._records = records
        self._max_record_changes_per_hour = max_record_changes_per_hour
        self._lock = asyncio.Lock()
        self._events: deque[float] = deque()
        self._rng = random.Random(seed)

    def _prune_events(self, now_epoch: float) -> None:
        while self._events and now_epoch - self._events[0] >= 3600:
            self._events.popleft()

    def _available_mutations(self, now_epoch: float) -> int:
        self._prune_events(now_epoch)
        return max(0, self._max_record_changes_per_hour - len(self._events))

    async def snapshot_sorted(self) -> list[CMDBRecord]:
        async with self._lock:
            copy_records = deepcopy(self._records)
        copy_records.sort(key=lambda r: r["sys_updated_on"])
        return copy_records

    async def mutate_once(self, requested: int) -> int:
        if requested <= 0:
            return 0

        now_epoch = datetime.now(UTC).timestamp()
        async with self._lock:
            allowance = self._available_mutations(now_epoch)
            if allowance <= 0:
                return 0

            max_changes = min(requested, allowance, len(self._records))
            if max_changes <= 0:
                return 0

            indices = self._rng.sample(range(len(self._records)), k=max_changes)
            now_str = datetime.now(UTC).strftime(TS_FORMAT)

            for idx in indices:
                record = self._records[idx]
                prev_updated_on = record["sys_updated_on"]
                prev_seg_tag = record["u_segmentation_group_tag"]
                prev_u_sync = record["u_sync"]
                prev_mod_count = record["sys_mod_count"]

                record["sys_updated_on"] = now_str
                record["u_segmentation_group_tag"] = (
                    f"cts:security-group-tag="
                    f"{self._rng.randint(1000,9999)}-{self._rng.randint(0,999):03d}"
                )
                record["u_sync"] = "true" if record["u_sync"] == "false" else "false"
                next_count = int(record["sys_mod_count"]) + self._rng.randint(1, 3)
                record["sys_mod_count"] = str(next_count)
                self._events.append(now_epoch)

                LOGGER.info(
                    "record_updated sys_id=%s sys_updated_on_old=%s sys_updated_on_new=%s "
                    "u_segmentation_group_tag_old=%s u_segmentation_group_tag_new=%s "
                    "u_sync_old=%s u_sync_new=%s sys_mod_count_old=%s sys_mod_count_new=%s",
                    record["sys_id"],
                    prev_updated_on,
                    record["sys_updated_on"],
                    prev_seg_tag,
                    record["u_segmentation_group_tag"],
                    prev_u_sync,
                    record["u_sync"],
                    prev_mod_count,
                    record["sys_mod_count"],
                )
            return max_changes
