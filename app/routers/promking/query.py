from __future__ import annotations

from datetime import datetime, date
from fastapi import APIRouter, HTTPException
from .db import get_pool
from ._models import QueryRequest

router = APIRouter(prefix="/query", tags=["promking:query"])


@router.post("")
async def execute_query(req: QueryRequest):
    sql_stripped = req.sql.strip().lower()
    
    # Simple check: must start with SELECT, or WITH ... SELECT (CTEs)
    # E.g. SELECT ..., WITH ... SELECT ...
    if not (sql_stripped.startswith("select") or ("select" in sql_stripped and sql_stripped.startswith("with"))):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed.")
        
    # Extra check to prevent data modifications like INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE
    dangerous_keywords = ["insert ", "update ", "delete ", "drop ", "alter ", "create ", "truncate ", "grant ", "revoke "]
    for kw in dangerous_keywords:
        if kw in sql_stripped:
            raise HTTPException(status_code=400, detail=f"Query contains forbidden keyword: {kw.strip().upper()}")

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(req.sql)
        
        def serialize_val(v):
            if isinstance(v, (datetime, date)):
                return v.isoformat()
            if isinstance(v, bytes):
                return v.decode("utf-8", errors="replace")
            return v

        return [
            {k: serialize_val(val) for k, val in dict(row).items()}
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
