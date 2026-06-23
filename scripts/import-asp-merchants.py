#!/usr/bin/env python3
"""ASP 가맹점 CSV → SQLite 임포트"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("ASP_DB_PATH", os.path.join(ROOT, "data", "asp_merchants.db"))

from app.api.asp_import import import_asp_csv, resolve_csv_path  # noqa: E402


def main() -> int:
    path = resolve_csv_path()
    if not path:
        print("CSV not found. Copy file to data/asp_merchant_usage.csv")
        return 1
    result = import_asp_csv(path, replace=True)
    print(result.get("message", result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
