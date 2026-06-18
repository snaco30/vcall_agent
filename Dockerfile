# 1. 패키지 저장소가 안정적인 데비안 Bullseye 기반의 파이썬 이미지로 변경
FROM python:3.10-slim-bullseye

# 2. 필수 패키지 및 드라이버 설치
RUN apt-get update && apt-get install -y \
    mdbtools \
    odbc-mdbtools \
    unixodbc \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. ODBC 드라이버 파일 설정 파일 등록
RUN echo "[Microsoft Access Driver (*.mdb, *.accdb)]\n\
Description=MDBTools Driver\n\
Driver=/usr/lib/x86_64-linux-gnu/odbc/libmdbodbc.so\n\
Setup=/usr/lib/x86_64-linux-gnu/odbc/libmdbodbc.so\n\
FileUsage=1" > /etc/odbcinst.ini

# 작업 디렉토리 설정
WORKDIR /code

# 💡 [핵심 최적화] 종속성 파일 복사 및 라이브러리 전체 클린 설치 (PyJWT, bcrypt 등 자동 포함)
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 앱 소스코드 복사
COPY ./app /code/app

# DB 파일이 매핑될 볼륨 디렉토리 생성
RUN mkdir /data

# 7001번 포트 개방 및 uvicorn 서버 실행
EXPOSE 7001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7001"]