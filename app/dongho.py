"""Giờ Việt Nam cho toàn app. Bài kiểm thử đặt `GIO_CO_DINH` để cố định "bây giờ"."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
GIO_CO_DINH: datetime | None = None


def bay_gio() -> datetime:
    """Giờ Việt Nam, không múi giờ (như mọi giờ lưu trong cơ sở dữ liệu)."""
    if GIO_CO_DINH is not None:
        return GIO_CO_DINH
    return datetime.now(VN).replace(tzinfo=None, microsecond=0)


def hom_nay() -> date:
    return bay_gio().date()


def doc_gio(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


def doc_ngay(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s[:10])


def ghi_gio(d: datetime) -> str:
    return d.replace(microsecond=0).isoformat(sep=" ")


def ngay_vn(d: date | datetime | None) -> str:
    """dd/mm/yyyy, như trường quen đọc."""
    return d.strftime("%d/%m/%Y") if d else ""


def gio_vn(d: datetime | None) -> str:
    return d.strftime("%d/%m/%Y %H:%M") if d else ""
