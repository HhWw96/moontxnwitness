from __future__ import annotations

from typing import Any

try:  # pragma: no cover - exercised indirectly in runtime environments
    import psycopg
    from psycopg import sql
except ModuleNotFoundError:  # pragma: no cover
    # Optional runtime dependency; require_psycopg() guards every use of these names.
    psycopg = None  # type: ignore[assignment]
    sql = None  # type: ignore[assignment]


def require_psycopg() -> None:
    if psycopg is None or sql is None:
        raise ModuleNotFoundError(
            "psycopg (v3) is required to use PostgreSQL-backed locks. "
            "Install dislock with its runtime dependencies."
        )


def make_qualified_table_name(parts: list[str]) -> Any:
    require_psycopg()
    return sql.SQL(".").join([sql.Identifier(part) for part in parts])


def acquire_lock_query(table_parts: list[str]) -> Any:
    t = make_qualified_table_name(table_parts)
    return sql.SQL(
        """
        INSERT INTO {t} (key, value, expire_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value,
            expire_at = EXCLUDED.expire_at
        WHERE {t}.expire_at <= NOW()
        RETURNING key, expire_at;
        """
    ).format(t=t)


def acquire_run_lock_query(table_parts: list[str]) -> Any:
    t = make_qualified_table_name(table_parts)
    return sql.SQL(
        """
        INSERT INTO {t} (key, value, expire_at)
        VALUES (%s, %s, NOW() + (%s * INTERVAL '1 second'))
        ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value,
            expire_at = EXCLUDED.expire_at
        WHERE {t}.expire_at <= NOW()
        RETURNING key, expire_at;
        """
    ).format(t=t)


def read_current_query(table_parts: list[str]) -> Any:
    t = make_qualified_table_name(table_parts)
    return sql.SQL(
        """
        SELECT expire_at, value
        FROM {t}
        WHERE key = %s;
        """
    ).format(t=t)


def renew_lease_query(table_parts: list[str]) -> Any:
    t = make_qualified_table_name(table_parts)
    return sql.SQL(
        """
        UPDATE {t}
        SET expire_at = NOW() + (%s * INTERVAL '1 second')
        WHERE key = %s
          AND value = %s
        RETURNING expire_at;
        """
    ).format(t=t)


def expire_lock_query(table_parts: list[str]) -> Any:
    t = make_qualified_table_name(table_parts)
    return sql.SQL(
        """
        UPDATE {t}
        SET expire_at = NOW()
        WHERE key = %s
          AND value = %s
        RETURNING key;
        """
    ).format(t=t)
