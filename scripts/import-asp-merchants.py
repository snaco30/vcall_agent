#!/usr/bin/env python3
"""ASP 가맹점 데이터 파일(txt/csv) → SQLite DB (관리자 CLI 전용)"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("ASP_DB_PATH", os.path.join(ROOT, "data", "asp_merchants.db"))

from app.api.asp_import import import_asp_file  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("사용법: python3 scripts/import-asp-merchants.py <txt_or_csv_path>")
        print("예: python3 scripts/import-asp-merchants.py data/asp가맹점\\ 사용현황.txt")
        return 1
    result = import_asp_file(sys.argv[1], replace=True)
    print(result.get("message", result))
    print(f"imported={result.get('imported')} skipped={result.get('skipped')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
