from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from contextlib import suppress

from aiohttp import web

from .config import Config
from .filters import FilterParseError, TS_FORMAT, parse_sys_updated_on_filters
from .store import CMDBStore, generate_records
from .tls import ensure_tls_context

LOGGER = logging.getLogger("cmdb-sim")


def create_app(config: Config) -> web.Application:
    app = web.Application()
    store = CMDBStore(
        records=generate_records(config.cmdb_record_count, seed=config.random_seed),
        max_record_changes_per_hour=config.max_record_changes_per_hour,
        seed=config.random_seed,
    )

    app["config"] = config
    app["store"] = store
    app["mutation_task"] = None

    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/v1/cmdb", get_cmdb)

    app.on_startup.append(start_mutation_loop)
    app.on_cleanup.append(stop_mutation_loop)
    return app


async def healthz(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def get_cmdb(request: web.Request) -> web.Response:
    store: CMDBStore = request.app["store"]

    try:
        predicates = parse_sys_updated_on_filters(request.query_string)
    except FilterParseError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    rows = await store.snapshot_sorted()
    if predicates:
        filtered = []
        for row in rows:
            dt = datetime.strptime(row["sys_updated_on"], TS_FORMAT)
            if all(predicate(dt) for predicate in predicates):
                filtered.append(row)
        rows = filtered

    return web.json_response({"result": rows})


async def start_mutation_loop(app: web.Application) -> None:
    cfg: Config = app["config"]
    if not cfg.mutation_enabled:
        LOGGER.info("Mutation worker disabled by configuration.")
        app["mutation_task"] = None
        return
    store: CMDBStore = app["store"]
    app["mutation_task"] = asyncio.create_task(
        _mutation_worker(
            store,
            tick_seconds=cfg.mutation_tick_seconds,
            max_mutations_per_tick=cfg.max_mutations_per_tick,
        )
    )
    LOGGER.info("Mutation worker started.")


async def stop_mutation_loop(app: web.Application) -> None:
    task: asyncio.Task | None = app["mutation_task"]
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    LOGGER.info("Mutation worker stopped.")


async def _mutation_worker(
    store: CMDBStore, tick_seconds: int, max_mutations_per_tick: int
) -> None:
    rng = random.Random()
    while True:
        requested = rng.randint(0, max_mutations_per_tick)
        await store.mutate_once(requested)
        await asyncio.sleep(tick_seconds)


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = Config.from_env()
    app = create_app(cfg)
    asyncio.run(run_servers(app, cfg))


async def run_servers(app: web.Application, cfg: Config) -> None:
    runner = web.AppRunner(app)
    await runner.setup()

    sites: list[web.BaseSite] = []
    try:
        if not cfg.tls_enabled or cfg.tls_keep_http_listener:
            http_site = web.TCPSite(runner, host=cfg.host, port=cfg.port)
            await http_site.start()
            sites.append(http_site)
            LOGGER.info("HTTP listening on %s:%d", cfg.host, cfg.port)

        if cfg.tls_enabled:
            ssl_context = ensure_tls_context(
                cert_path=cfg.tls_cert_file,
                key_path=cfg.tls_key_file,
                auto_generate=cfg.tls_auto_generate,
            )
            https_site = web.TCPSite(
                runner, host=cfg.host, port=cfg.tls_port, ssl_context=ssl_context
            )
            await https_site.start()
            sites.append(https_site)
            LOGGER.info("HTTPS listening on %s:%d", cfg.host, cfg.tls_port)

        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        LOGGER.info("Shutting down server")
    finally:
        for site in sites:
            with suppress(Exception):
                await site.stop()
        await runner.cleanup()


if __name__ == "__main__":
    run()
