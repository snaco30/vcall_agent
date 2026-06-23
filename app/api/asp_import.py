import csv
import json
import os
import re
from pathlib import Path

from app.api.asp_db import get_connection, init_asp_db

CSV_CANDIDATES = (
    os.getenv("ASP_MERCHANT_CSV_PATH", ""),
    "/data/asp_merchant_usage.csv",
    "/data/asp가맹점 사용현황.csv",
    "data/asp_merchant_usage.csv",
    "data/asp가맹점 사용현황.csv",
)

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "merchant_name": (
        "거래처(상호)", "거래처상호", "거래처 상호", "상호", "상호명", "가맹점상호", "가맹점명",
        "거래처명", "매장명", "mername", "merchantname",
    ),
    "saup_no": ("사업자번호", "사업자등록번호", "사업자등록 번호", "사업자 번호", "saupno"),
    "presi_name": ("대표자", "대표자명", "대표", "presiname"),
    "tel_no": ("전화", "전화번호", "연락처", "휴대폰", "핸드폰", "telno", "tel"),
    "addr": ("주소", "소재지", "addr", "address"),
    "asp_provider": ("asp사", "asp업체", "asp명", "제공사"),
    "merchant_id": ("aspid", "asp id", "가맹점번호", "mid", "merchantid", "가맹점id", "아이디"),
    "terminal_id": ("터미널번호", "tid", "terminalid", "단말기번호"),
    "asp_join_date": ("신청일자", "asp가입일", "가입일", "가입일자", "등록일", "개통일", "날짜"),
    "usage_status": ("사용현황", "이용현황", "상태", "사용상태", "가입현황"),
    "van_type": ("van", "van사", "밴사", "밴"),
    "damdang": ("담당", "담당자", "영업담당", "관리담당"),
    "bigo": ("비고", "메모", "remark", "note"),
}

DB_COLUMNS = tuple(FIELD_ALIASES.keys())


def _normalize_header(value: str) -> str:
    text = (value or "").replace("\ufeff", "").strip().lower()
    text = re.sub(r"[\s_()（）]+", "", text)
    return text


def _build_header_map(headers: list[str]) -> dict[str, str]:
    alias_lookup: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            alias_lookup[_normalize_header(alias)] = field

    mapping: dict[str, str] = {}
    for header in headers:
        normalized = _normalize_header(header)
        if normalized in alias_lookup:
            mapping[header] = alias_lookup[normalized]
    return mapping


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\x00", "").replace("\ufeff", "").strip()


def _read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = csv_path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"CSV 인코딩을 읽을 수 없습니다: {csv_path}")

    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError(f"CSV 헤더가 없습니다: {csv_path}")

    headers = [h for h in reader.fieldnames if h]
    rows: list[dict[str, str]] = []
    for row in reader:
        if not row:
            continue
        cleaned = {_clean_cell(k): _clean_cell(v) for k, v in row.items() if k}
        if any(cleaned.values()):
            rows.append(cleaned)
    return headers, rows


def resolve_csv_path() -> Path | None:
    seen: set[str] = set()
    for candidate in CSV_CANDIDATES:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def import_asp_csv(csv_path: Path | str | None = None, replace: bool = True) -> dict:
    init_asp_db()
    path = Path(csv_path) if csv_path else resolve_csv_path()
    if not path or not path.is_file():
        return {
            "ok": False,
            "message": "ASP CSV 파일을 찾을 수 없습니다. data/asp_merchant_usage.csv 에 복사해 주세요.",
            "imported": 0,
            "skipped": 0,
            "csv_path": None,
        }

    headers, rows = _read_csv_rows(path)
    header_map = _build_header_map(headers)

    if "merchant_name" not in header_map.values():
        first_header = headers[0]
        header_map[first_header] = "merchant_name"

    records: list[dict] = []
    skipped = 0
    for row in rows:
        record = {field: "" for field in DB_COLUMNS}
        extras: dict[str, str] = {}
        for header, value in row.items():
            field = header_map.get(header)
            if field:
                record[field] = value
            elif header and value:
                extras[header] = value

        if not record["merchant_name"] and extras:
            for key, value in extras.items():
                if value:
                    record["merchant_name"] = value
                    extras.pop(key, None)
                    break

        if not record["merchant_name"]:
            skipped += 1
            continue

        join_date = record.get("asp_join_date", "")
        if join_date and (join_date.endswith("-00") or join_date in ("1900-01-00", "1900-00-00", "2000-01-00")):
            record["asp_join_date"] = ""

        record["extras"] = json.dumps(extras, ensure_ascii=False)
        records.append(record)

    if not records:
        return {
            "ok": False,
            "message": "가져올 유효한 행이 없습니다.",
            "imported": 0,
            "skipped": skipped,
            "csv_path": str(path),
        }

    with get_connection() as conn:
        if replace:
            conn.execute("DELETE FROM asp_merchants")
        conn.executemany(
            """
            INSERT INTO asp_merchants (
                merchant_name, saup_no, presi_name, tel_no, addr,
                asp_provider, merchant_id, terminal_id, asp_join_date,
                usage_status, van_type, damdang, bigo, extras
            ) VALUES (
                :merchant_name, :saup_no, :presi_name, :tel_no, :addr,
                :asp_provider, :merchant_id, :terminal_id, :asp_join_date,
                :usage_status, :van_type, :damdang, :bigo, :extras
            )
            """,
            records,
        )
        conn.commit()

    return {
        "ok": True,
        "message": f"{len(records)}건을 가져왔습니다.",
        "imported": len(records),
        "skipped": skipped,
        "csv_path": str(path),
        "headers": headers,
    }


def maybe_import_on_startup() -> dict | None:
    if asp_row_count_safe() > 0:
        return None
    path = resolve_csv_path()
    if not path:
        return None
    return import_asp_csv(path, replace=True)


def asp_row_count_safe() -> int:
    try:
        init_asp_db()
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM asp_merchants").fetchone()
            return int(row["cnt"]) if row else 0
    except Exception:
        return 0
