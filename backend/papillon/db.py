"""Thin Postgres layer. The backend talks to PostgreSQL on the VPS directly."""

import json
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from .config import cfg

pool: AsyncConnectionPool | None = None


async def open_pool(url: str | None = None) -> None:
    global pool
    pool = AsyncConnectionPool(
        url or cfg.database_url,
        min_size=1,
        max_size=10,
        open=False,
        # no prepared statements: also works behind connection poolers
        kwargs={"row_factory": dict_row, "autocommit": True, "prepare_threshold": None},
    )
    await pool.open(wait=True)


async def close_pool() -> None:
    if pool:
        await pool.close()


def _adapt(params):
    if params is None:
        return None
    if isinstance(params, dict):
        return {k: (Jsonb(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
    return [Jsonb(v) if isinstance(v, (dict, list)) else v for v in params]


async def fetchone(sql: str, params: Any = None) -> dict | None:
    async with pool.connection() as conn:
        cur = await conn.execute(sql, _adapt(params))
        return await cur.fetchone()


async def fetchall(sql: str, params: Any = None) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(sql, _adapt(params))
        return await cur.fetchall()


async def execute(sql: str, params: Any = None) -> None:
    async with pool.connection() as conn:
        await conn.execute(sql, _adapt(params))


async def log_event(lead_id, kind: str, detail: dict | None = None, actor: str = "system") -> None:
    await execute(
        "insert into lead_events (lead_id, kind, detail, actor) values (%s, %s, %s, %s)",
        [lead_id, kind, detail or {}, actor],
    )


async def get_settings() -> dict:
    return await fetchone("select * from settings where id = 1")


async def get_lead(lead_id) -> dict | None:
    return await fetchone("select * from leads where id = %s", [lead_id])


LEAD_FIELDS = {
    "name", "email", "lives_in", "property_type", "project_name", "project_id", "locality", "city",
    "configuration", "area_sqft", "possession_status", "scope", "scope_detail", "budget_min",
    "budget_max", "budget_said", "timeline", "ownership", "decision_maker", "other_designers",
    "willing_consultation", "consult_mode", "consult_slot", "consult_slot_said", "language",
    "ai_summary", "notes", "status", "temperature", "score", "score_reasons", "disqualify_reason",
    "channel", "call_attempts", "next_call_at", "last_contact_at", "qualified_at", "stage",
    "forwarded_at", "stage_updated_at",
}


async def update_lead(lead_id, **fields) -> dict | None:
    fields = {k: v for k, v in fields.items() if k in LEAD_FIELDS}
    if not fields:
        return await get_lead(lead_id)
    sets = ", ".join(f"{k} = %({k})s" for k in fields)
    fields["_id"] = lead_id
    return await fetchone(f"update leads set {sets} where id = %(_id)s returning *", fields)


def dumps(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)
