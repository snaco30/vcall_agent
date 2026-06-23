import csv
import json
import re
from io import StringIO
from pathlib import Path

from app.api.asp_db import _harden_db_file_permissions, get_connection, init_asp_db

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


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp949", "euc-kr", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("파일 인코딩을 읽을 수 없습니다.")


def _detect_delimiter(sample_line: str) -> str:
    if "\t" in sample_line:
        return "\t"
    if ";" in sample_line and sample_line.count(";") >= sample_line.count(","):
        return ";"
    return ","


def _read_tabular_rows(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = _decode_bytes(raw)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("데이터가 비어 있습니다.")

    delimiter = _detect_delimiter(lines[0])
    reader = csv.reader(StringIO("\n".join(lines)), delimiter=delimiter)
    table = [row for row in reader if any(cell.strip() for cell in row)]
    if not table:
        raise ValueError("유효한 행이 없습니다.")

    headers = [_clean_cell(cell) for cell in table[0]]
    rows: list[dict[str, str]] = []
    for row in table[1:]:
        if not row:
            continue
        padded = row + [""] * max(0, len(headers) - len(row))
        cleaned = {
            headers[idx]: _clean_cell(padded[idx])
            for idx in range(len(headers))
            if headers[idx]
        }
        if any(cleaned.values()):
            rows.append(cleaned)
    return headers, rows


def _rows_to_records(headers: list[str], rows: list[dict[str, str]]) -> tuple[list[dict], int]:
    header_map = _build_header_map(headers)
    if "merchant_name" not in header_map.values() and headers:
        header_map[headers[0]] = "merchant_name"

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
    return records, skipped


def _insert_records(records: list[dict], replace: bool = True) -> None:
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
    _harden_db_file_permissions()


def import_asp_bytes(raw: bytes, replace: bool = True) -> dict:
    """CLI/관리 스크립트 전용 — 웹 API에서 호출하지 않습니다."""
    init_asp_db()
    try:
        headers, rows = _read_tabular_rows(raw)
    except ValueError as exc:
        return {"ok": False, "message": str(exc), "imported": 0, "skipped": 0}

    records, skipped = _rows_to_records(headers, rows)
    if not records:
        return {
            "ok": False,
            "message": "가져올 유효한 행이 없습니다.",
            "imported": 0,
            "skipped": skipped,
        }

    _insert_records(records, replace=replace)
    return {
        "ok": True,
        "message": f"{len(records)}건을 DB에 저장했습니다.",
        "imported": len(records),
        "skipped": skipped,
    }


def import_asp_file(data_path: Path | str, replace: bool = True) -> dict:
    """CLI/관리 스크립트 전용 — 파일 내용을 DB로 복사합니다."""
    path = Path(data_path)
    if not path.is_file():
        return {
            "ok": False,
            "message": f"파일을 찾을 수 없습니다: {path}",
            "imported": 0,
            "skipped": 0,
        }
    return import_asp_bytes(path.read_bytes(), replace=replace)
