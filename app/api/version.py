from fastapi import APIRouter

from app.version import get_version_info

router = APIRouter(prefix="/api", tags=["Version"])


@router.get("/version")
def read_version_info():
    return get_version_info()
