from fastapi import APIRouter, Query, Depends, HTTPException, status
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
        # mdb-export 엔진 가동 및 인코딩 처리
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
    current_user: str = Depends(get_current_user)  # 💡 비로그인 접근 차단 보안 장치
):
    search_keyword = search.strip()
    if not search_keyword:
        return []

    # 1. TMER2 (가맹점 마스터 테이블) 추출
    tmer2_csv, err = get_clean_table_data("TMER2")