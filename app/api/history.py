from fastapi import APIRouter, Query, Depends
import csv
import io
# merchants.py 모듈에 구성된 고정 유틸리티 함수들을 참조 연동하여 중복 코드 최소화
from app.api.merchants import get_clean_table_data, clean_text, format_datetime
from app.api.auth import get_current_user  # JWT 보안 주입

router = APIRouter(prefix="/api/history", tags=["History"])

@router.get("")
def get_history(
    saup_no: str = Query("", description="사업자번호 기반 매핑 조건"), 
    tel_no: str = Query("", description="전화번호 기반 매핑 조건"),
    current_user: str = Depends(get_current_user)  # 💡 비로그인 접근 차단 보안 장치
):
    if not saup_no and not tel_no:
        return []
    
    # 1. TCALLCONTENT2 (대용량 통화기록 상세 테이블) 스트림 추출
    tcall_csv, err = get_clean_table_data("TCALLCONTENT2")
    if err or not tcall_csv:
        return []
        
    f = io.StringIO(tcall_csv.strip())
    reader = csv.reader(f)
    next(reader, None)  # CSV 헤더 로우 패스
    
    history = []
    for row in reader:
        try:
            # 최소 21개 이상으로 구조화된 MDB 테이블 컬럼 배열 검증
            if len(row) < 21: 
                continue
            
            r_saup = clean_text(row[1])
            r_tel = clean_text(row[3])
            
            # 사업자번호 일치 혹은 전화번호 역매핑 스캔 (하이픈 제거 비교로 정확도 보정)
            match = False
            if saup_no and r_saup == saup_no: 
                match = True
            if tel_no and r_tel.replace("-", "") == tel_no.replace("-", ""): 
                match = True
                
            if not match: 
                continue
                
            # 17개 핵심 전수 칼럼 데이터 맵 바인딩
            history.append({
                "tel_no": r_tel,
                "regi_time": format_datetime(clean_text(row[11])),
                "mer_name": clean_text(row[2]),
                "content": clean_text(row[14]),
                "upmu_type": clean_text(row[4]),
                "upmu_det": clean_text(row[16]),
                "proc_type": clean_text(row[5]),
                "res": clean_text(row[15]),
                "proc_name": clean_text(row[8]),
                "ok_yn": clean_text(row[20]),
                "snd_name": clean_text(row[6]),
                "prev_name": clean_text(row[9]),
                "takeover": clean_text(row[10]),
                "churi_time": format_datetime(clean_text(row[13])),
                "after_type": clean_text(row[17]),
                "after_det": clean_text(row[18]),
                "before_time": clean_text(row[19])
            })
        except:
            continue
            
    # 최근 통화 기록이 리스트 최상단에 먼저 보이도록 역순 정렬 처리
    history.reverse()
    return history