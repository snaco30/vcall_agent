import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.asp_db import get_connection, init_asp_db
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/asp-merchants", tags=["AspMerchants"])

DB_COLUMNS = (
    "merchant_name", "saup_no", "presi_name", "tel_no", "addr",
    "asp_provider", "merchant_id", "terminal_id", "asp_join_date",
    "usage_status", "van_type", "damdang", "bigo", "extras",
)


class AspMerchantBase(BaseModel):
    merchant_name: str = ""
    saup_no: str = ""
    presi_name: str = ""
    tel_no: str = ""
    addr: str = ""
    asp_provider: str = ""
    merchant_id: str = ""
    terminal_id: str = ""
    asp_join_date: str = ""
    usage_status: str = ""
    van_type: str = ""
    damdang: str = ""
    bigo: str = ""
    extras: dict = Field(default_factory=dict)


class AspMerchantCreate(AspMerchantBase):
    merchant_name: str


class AspMerchantUpdate(AspMerchantBase):
    pass


def _row_to_dict(row) -> dict:
    data = {key: row[key] for key in row.keys() if key not in ("created_at", "updated_at")}
    try:
        data["extras"] = json.loads(data.get("extras") or "{}")
    except json.JSONDecodeError:
        data["extras"] = {}
    return data


def _prepare_payload(payload: AspMerchantBase) -> dict:
    data = payload.model_dump()
    if not data.get("merchant_name", "").strip():
        raise HTTPException(status_code=400, detail="거래처 상호는 필수입니다.")
    data["merchant_name"] = data["merchant_name"].strip()
    data["extras"] = json.dumps(data.get("extras") or {}, ensure_ascii=False)
    return data


def bootstrap_asp_data() -> None:
    """런타임에는 SQLite DB만 사용합니다. 원본 txt/csv는 읽지 않습니다."""
    init_asp_db()


@router.get("")
def list_asp_merchants(
    search: str = Query("", description="거래처 상호 부분 검색"),
    limit: int = Query(200, ge=1, le=1000),
    current_user: str = Depends(get_current_user),
):
    init_asp_db()
    keyword = search.strip()
    sql = """
        SELECT id, merchant_name, saup_no, presi_name, tel_no, addr,
               asp_provider, merchant_id, terminal_id, asp_join_date,
               usage_status, van_type, damdang, bigo, extras
        FROM asp_merchants
    """
    params: list = []
    if keyword:
        sql += " WHERE merchant_name LIKE ? ESCAPE '\\' COLLATE NOCASE"
        safe = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{safe}%")
    sql += " ORDER BY merchant_name COLLATE NOCASE ASC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


@router.get("/meta")
def asp_merchants_meta(current_user: str = Depends(get_current_user)):
    init_asp_db()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM asp_merchants").fetchone()["cnt"]
    return {"count": int(count)}


@router.get("/{merchant_id}")
def get_asp_merchant(merchant_id: int, current_user: str = Depends(get_current_user)):
    init_asp_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM asp_merchants WHERE id = ?",
            (merchant_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
    return _row_to_dict(row)


@router.post("")
def create_asp_merchant(
    payload: AspMerchantCreate,
    current_user: str = Depends(get_current_user),
):
    init_asp_db()
    data = _prepare_payload(payload)
    columns = ", ".join(DB_COLUMNS)
    placeholders = ", ".join(f":{col}" for col in DB_COLUMNS)
    with get_connection() as conn:
        cur = conn.execute(
            f"""
            INSERT INTO asp_merchants ({columns})
            VALUES ({placeholders})
            """,
            data,
        )
        conn.commit()
        row_id = cur.lastrowid
        row = conn.execute("SELECT * FROM asp_merchants WHERE id = ?", (row_id,)).fetchone()
    return _row_to_dict(row)


@router.put("/{merchant_id}")
def update_asp_merchant(
    merchant_id: int,
    payload: AspMerchantUpdate,
    current_user: str = Depends(get_current_user),
):
    init_asp_db()
    data = _prepare_payload(payload)
    assignments = ", ".join(f"{col} = :{col}" for col in DB_COLUMNS)
    data["id"] = merchant_id
    with get_connection() as conn:
        cur = conn.execute(
            f"""
            UPDATE asp_merchants
            SET {assignments},
                updated_at = datetime('now', 'localtime')
            WHERE id = :id
            """,
            data,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
        conn.commit()
        row = conn.execute("SELECT * FROM asp_merchants WHERE id = ?", (merchant_id,)).fetchone()
    return _row_to_dict(row)


@router.delete("/{merchant_id}")
def delete_asp_merchant(merchant_id: int, current_user: str = Depends(get_current_user)):
    init_asp_db()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM asp_merchants WHERE id = ?", (merchant_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
    return {"ok": True}
