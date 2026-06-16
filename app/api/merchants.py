from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
import csv
import io
import os
import subprocess
from app.api.auth import get_current_user  # JWT 보안 주입

router = APIRouter(prefix="/api/merchants", tags=["Merchants"])

MDB_PATH = "/data/vanpro97_call.mdb"

class MerchantUpdate(BaseModel):
    name: str
    tel_no: str
    saup_no: str = ""
    damdang: str = ""
    bigo: str = ""

def get_clean_table_data(table_name: str):
    """MDB 덤프 추출 및 제어 문자를 정제하는 공통 핵심 함수"""
    if not os.path.exists(MDB_PATH):
        return None, "MDB 파일이 /data 경로에 존재하지 않습니다."
    try:
        result = subprocess.run(
            ["mdb-export", "-D", "%Y-%m-%d %H:%M:%S", MDB_PATH, table_name],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        return result.stdout, None
    except subprocess.CalledProcessError as e:
        return None, f"MDB mdb-export 테이블 추출 실패: {e.stderr}"
    except Exception as e:
        return None, str(e)

def clean_text(val: str) -> str:
    """바이너리 널바이트(\x00) 및 유니코드 BOM 제어 문자 필터링"""
    if not val:
        return ""
    return val.replace('\x00', '').replace('\ufeff', '').strip()

def format_datetime(val: str) -> str:
    """텍스트 기반 날짜 포맷을 YYYY-MM-DD HH:MM:SS 표준 양식으로 교정"""
    if not val:
        return "-"
    val = val.strip()
    if len(val) == 8 and val.isdigit():
        return f"{val[0:4]}-{val[4:6]}-{val[6:8]}"
    elif len(val) >= 14 and ":" not in val and val[:14].isdigit():
        return f"{val[0:4]}-{val[4:6]}-{val[6:8]} {val[8:10]}:{val[10:12]}:{val[12:14]}"
    return val

@router.get("")
def get_merchants(
    search: str = Query("", description="검색 키워드 (상호, 번호, 대표자, 사업자번호)"),
    current_user: str = Depends(get_current_user)
):
    search_keyword = search.strip().lower()
    if not search_keyword:
        return []

    tmer2_csv, err = get_clean_table_data("TMER2")
    if err or not tmer2_csv:
        return []

    f = io.StringIO(tmer2_csv)
    reader = csv.DictReader(f)
    merchants = []

    for row in reader:
        if not row:
            continue

        saup_no = clean_text(row.get("SAUPNO", "") or row.get("saupno", ""))
        mer_name = clean_text(row.get("MERNAME", "") or row.get("mername", ""))
        presi_name = clean_text(row.get("PRESINAME", "") or row.get("presiname", ""))
        addr = clean_text(row.get("ADDR", "") or row.get("addr", ""))
        zip_no = clean_text(row.get("ZIPNO", "") or row.get("zipno", ""))
        tel_no = clean_text(row.get("TELNO", "") or row.get("telno", ""))
        regi_date = format_datetime(clean_text(row.get("REGIYMD", "") or row.get("regiymd", "")))
        presi_rate = clean_text(row.get("PRESIRATE", "") or row.get("presirate", ""))
        damdang = clean_text(row.get("DAMDANG", "") or row.get("damdang", ""))
        bigo = clean_text(row.get("BIGO", "") or row.get("bigo", ""))
        delay_info = clean_text(row.get("DELAYINFO", "") or row.get("delayinfo", "")) or "정상"

        match_text = " ".join([saup_no, mer_name, presi_name, tel_no, addr, damdang, bigo, delay_info]).lower()
        if search_keyword not in match_text:
            continue

        merchants.append({
            "saup_no": saup_no,
            "name": mer_name,
            "presi_name": presi_name,
            "addr": addr,
            "zip_no": zip_no,
            "tel_no": tel_no,
            "regi_date": regi_date,
            "mer_type": presi_rate,
            "damdang": damdang,
            "bigo": bigo,
            "delay_info": delay_info
        })

    return merchants
