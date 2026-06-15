from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import subprocess
import csv
import io

app = FastAPI(title="가맹점 마스터 및 이력 관리 시스템")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MDB_PATH = "/data/vanpro97_call.mdb"

class MerchantUpdate(BaseModel):
    name: str
    tel_no: str
    saup_no: str = ""
    damdang: str = ""
    bigo: str = ""

@app.get("/")
def read_index():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(current_dir, "index.html"))

# 💡 순수 UTF-8 텍스트를 왜곡 없이 가져오는 추출 엔진
def get_clean_table_data(table_name: str):
    if not os.path.exists(MDB_PATH):
        return None, "MDB 파일 유실"
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
        return None, f"추출 실패: {e.stderr}"
    except Exception as e:
        return None, str(e)

# 유령 제어문자 청소 필터
def clean_text(val: str) -> str:
    if not val: return ""
    return val.replace('\x00', '').replace('\ufeff', '').strip()

# 날짜/시간 가독성 포맷팅 함수
def format_datetime(val: str) -> str:
    if not val: return "-"
    if len(val) == 8: # YYYYMMDD
        return f"{val[0:4]}-{val[4:6]}-{val[6:8]}"
    elif len(val) >= 14 and ":" not in val: # YYYYMMDDHHMMSS
        return f"{val[0:4]}-{val[4:6]}-{val[6:8]} {val[8:10]}:{val[10:12]}:{val[12:14]}"
    return val

@app.get("/api/merchants")
def get_merchants(search: str = ""):
    search_keyword = search.strip()
    if not search_keyword:
        return []

    tmer2_csv, err = get_clean_table_data("TMER2")
    if err or not tmer2_csv:
        return []

    f = io.StringIO(tmer2_csv.strip())
    reader = csv.reader(f)
    next(reader, None)

    result = []
    for idx, row in enumerate(reader):
        try:
            if len(row) < 11:
                continue

            r_saup = clean_text(row[0])      # 사업자번호
            r_name = clean_text(row[1])      # 상호
            r_presi = clean_text(row[2])     # 대표자
            r_addr = clean_text(row[3])      # 주소
            r_tel = clean_text(row[5])       # 전화번호
            r_regi = clean_text(row[6])      # 등록일자 (REGIYMD)
            r_type = clean_text(row[7])      # 업체유형 (PRESIRATE 매핑)
            r_damdang = clean_text(row[8])   # 관리담당자 (DAMDANG)
            r_bigo = clean_text(row[9])      # 비고
            r_delay = clean_text(row[10])    # 연체정보

            if not r_saup and not r_name and not r_tel:
                continue

            s_l = search_keyword.lower()
            if (s_l not in r_name.lower() and 
                s_l not in r_saup.lower() and 
                s_l not in r_tel.lower() and 
                s_l not in r_presi.lower()):
                continue

            # 💡 기존 7개 + 추가된 3개(업체유형, 등록일자, 관리담당자) 데이터 셋 조립
            result.append({
                "code": f"M{idx+1:04d}",
                "saup_no": r_saup,
                "name": r_name,
                "tel_no": r_tel,
                "addr": r_addr,
                "mer_type": r_type if r_type else "-",            # 업체유형
                "regi_date": format_datetime(r_regi),             # 등록일자
                "damdang": r_damdang if r_damdang else "-",       # 관리담당자
                "presi_name": r_presi,
                "delay_info": r_delay if r_delay else "정상",
                "bigo": r_bigo if r_bigo else "-"
            })
        except:
            continue

    return result

# 💡 [신규 추가] 특정 가맹점의 전체 통화 이력을 17개 항목으로 뽑아오는 API
@app.get("/api/history")
def get_history(saup_no: str = "", tel_no: str = ""):
    if not saup_no and not tel_no:
        return []
    
    tcall_csv, err = get_clean_table_data("TCALLCONTENT2")
    if err or not tcall_csv:
        return []
        
    f = io.StringIO(tcall_csv.strip())
    reader = csv.reader(f)
    next(reader, None)
    
    history = []
    for row in reader:
        try:
            if len(row) < 21: continue
            
            r_saup = clean_text(row[1])
            r_tel = clean_text(row[3])
            
            # 사업자번호나 전화번호가 하나라도 일치하면 해당 이력으로 간주
            match = False
            if saup_no and r_saup == saup_no: match = True
            if tel_no and r_tel.replace("-", "") == tel_no.replace("-", ""): match = True
                
            if not match: continue
                
            # 사장님이 요청하신 17개 컬럼 매핑
            history.append({
                "tel_no": r_tel,                           # 1. 전화번호
                "regi_time": format_datetime(clean_text(row[11])), # 2. 통화일시
                "mer_name": clean_text(row[2]),            # 3. 상호
                "content": clean_text(row[14]),            # 4. 통화내용
                "upmu_type": clean_text(row[4]),           # 5. 업무유형
                "upmu_det": clean_text(row[16]),           # 6. 업무상세
                "proc_type": clean_text(row[5]),           # 7. 처리상태
                "res": clean_text(row[15]),                # 8. 처리결과
                "proc_name": clean_text(row[8]),           # 9. 처리자
                "ok_yn": clean_text(row[20]),              # 10. 확인여부
                "snd_name": clean_text(row[6]),            # 11. 전화건사람
                "prev_name": clean_text(row[9]),           # 12. 전처리자
                "takeover": clean_text(row[10]),           # 13. 인계자
                "churi_time": format_datetime(clean_text(row[13])),# 14. 처리일시
                "after_type": clean_text(row[17]),         # 15. 사후처리
                "after_det": clean_text(row[18]),          # 16. 사후처리상세
                "before_time": clean_text(row[19])         # 17. 이전통화
            })
        except:
            continue
            
    # 최신 내역이 상단에 오도록 역순 정렬
    history.reverse()
    return history

@app.put("/api/merchants/{code}")
def update_merchant(code: str, data: MerchantUpdate):
    return {"success": True, "message": "성공"}