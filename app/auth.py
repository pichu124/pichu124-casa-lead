"""Mật khẩu (scrypt của thư viện chuẩn), khoá đăng nhập sai nhiều lần, mã chống giả mạo biểu mẫu."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

N, R, P = 2**14, 8, 1
MAT_KHAU_TOI_THIEU = 8


def bam(mat_khau: str) -> str:
    muoi = os.urandom(16)
    h = hashlib.scrypt(mat_khau.encode(), salt=muoi, n=N, r=R, p=P, dklen=32)
    return "scrypt$" + base64.b64encode(muoi).decode() + "$" + base64.b64encode(h).decode()


def dung_mat_khau(mat_khau: str, da_bam: str) -> bool:
    try:
        kieu, muoi, h = da_bam.split("$")
        if kieu != "scrypt":
            return False
        thu = hashlib.scrypt(mat_khau.encode(), salt=base64.b64decode(muoi), n=N, r=R, p=P, dklen=32)
        return hmac.compare_digest(thu, base64.b64decode(h))
    except Exception:
        return False


# Đăng nhập sai 5 lần trong 15 phút thì khoá tên đăng nhập đó 15 phút (giữ trong bộ nhớ: khởi động
# lại thì mở khoá, chấp nhận được với 7 người dùng).
SAI_TOI_DA, CUA_SO = 5, 15 * 60
_lan_sai: dict[str, list[float]] = {}


def bi_khoa(ten: str) -> bool:
    bay_gio = time.monotonic()
    ds = [t for t in _lan_sai.get(ten.lower(), []) if bay_gio - t < CUA_SO]
    _lan_sai[ten.lower()] = ds
    return len(ds) >= SAI_TOI_DA


def ghi_sai(ten: str) -> None:
    _lan_sai.setdefault(ten.lower(), []).append(time.monotonic())


def xoa_sai(ten: str) -> None:
    _lan_sai.pop(ten.lower(), None)


def khoa_phien(thu_muc: Path) -> str:
    """Khoá ký cookie phiên: biến CASA_LEAD_SECRET, không có thì tạo một lần và giữ trong thư mục dữ liệu."""
    tu_bien = os.environ.get("CASA_LEAD_SECRET")
    if tu_bien:
        return tu_bien
    p = thu_muc / "khoa-phien.txt"
    if p.exists():
        return p.read_text().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    khoa = secrets.token_urlsafe(48)
    p.write_text(khoa)
    os.chmod(p, 0o600)
    return khoa


def ma_bieu_mau(phien: dict) -> str:
    if "csrf" not in phien:
        phien["csrf"] = secrets.token_urlsafe(24)
    return phien["csrf"]


def dung_ma_bieu_mau(phien: dict, ma: str | None) -> bool:
    return bool(ma) and "csrf" in phien and hmac.compare_digest(phien["csrf"], ma)
