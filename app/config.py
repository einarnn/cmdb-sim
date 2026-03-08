from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = int(raw)
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    tls_enabled: bool
    tls_port: int
    tls_cert_file: str
    tls_key_file: str
    tls_auto_generate: bool
    tls_keep_http_listener: bool
    cmdb_record_count: int
    max_record_changes_per_hour: int
    mutation_tick_seconds: int
    max_mutations_per_tick: int
    random_seed: int
    mutation_enabled: bool

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            host=os.getenv("CMDB_HOST", "0.0.0.0"),
            port=_env_int("CMDB_PORT", 8080, minimum=1),
            tls_enabled=_env_bool("TLS_ENABLED", False),
            tls_port=_env_int("TLS_PORT", 8443, minimum=1),
            tls_cert_file=os.getenv("TLS_CERT_FILE", "/tmp/cmdb-cert.pem"),
            tls_key_file=os.getenv("TLS_KEY_FILE", "/tmp/cmdb-key.pem"),
            tls_auto_generate=_env_bool("TLS_AUTO_GENERATE_CERTS", True),
            tls_keep_http_listener=_env_bool("TLS_KEEP_HTTP_LISTENER", True),
            cmdb_record_count=_env_int("CMDB_RECORD_COUNT", 1000, minimum=1),
            max_record_changes_per_hour=_env_int(
                "MAX_RECORD_CHANGES_PER_HOUR", 1000, minimum=1
            ),
            mutation_tick_seconds=_env_int("MUTATION_TICK_SECONDS", 5, minimum=1),
            max_mutations_per_tick=_env_int("MAX_MUTATIONS_PER_TICK", 5, minimum=0),
            random_seed=_env_int("CMDB_RANDOM_SEED", 42, minimum=0),
            mutation_enabled=_env_bool("MUTATION_ENABLED", True),
        )
