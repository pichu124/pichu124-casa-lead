"""Lead website: đọc tệp đăng ký tham quan mà dịch vụ form của website ghi, để chủ giao cho sale.

Dịch vụ form của website (repo pichu124-casa-website, thư mục form/) ghi mỗi đăng ký một dòng JSON vào
`/var/lib/casa-website/dang-ky.jsonl` trên cùng VPS. App chỉ ĐỌC tệp đó (không ghi, không xoá, không gọi
dịch vụ form). Quyền đọc cấp riêng cho user chạy app bằng ACL: docs/TRIEN-KHAI.md mục "Lead website".

Mỗi dòng (khóa do website đặt): thoi_gian (ISO, UTC), ten, sdt, thang_sinh, nam_sinh, co_so (mã: kim-ma,
chua-lang, my-dinh, ciputra, chua-chon), ngon_ngu (vi/en), biet_qua (mã, có thể rỗng), nguon (nguồn truy
cập: ?nguon= hoặc "ref-<tên miền>", có thể rỗng), dong_y, email ("da-gui"/"loi": trạng thái email báo
tuyển sinh, KHÔNG phải email phụ huynh).

Biến môi trường: CASA_WEBSITE_DANG_KY (đường dẫn tệp; mặc định như trên). Bản sao các dòng nằm trong bảng
`website` (mã = băm của thời gian + SĐT). Lead đã giao là lead có `lead.website_id` trùng; chủ có thể
"bỏ qua" dòng không phải lead thật (đăng ký thử, trùng).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, dongho, logic

log = logging.getLogger("casa_lead.website")

TEP_MAC_DINH = "/var/lib/casa-website/dang-ky.jsonl"

# Mã cơ sở của form website → tên trong danh mục Cơ sở của app. "chua-chon", "ciputra": để trống, sale hỏi lại
# (Ciputra chưa có trong danh mục; app chỉ điền khi tên có trong danh mục).
CO_SO = {"kim-ma": "Kim Mã", "chua-lang": "Chùa Láng", "my-dinh": "Mỹ Đình", "ciputra": "Ciputra"}

# Ô "Biết Casa qua" của form → danh mục Nguồn (người phụ trách dự án chốt 27/11/2026). Không chọn → "Website".
NGUON = {"google": "Google (tìm kiếm)", "google-maps": "Google Maps", "facebook": "Facebook", "zalo": "Zalo",
         "nguoi-quen": "Giới thiệu", "di-ngang-qua": "Tự biết tới trường", "khac": "Khác"}
NGUON_KHONG_CHON = "Website"
TEN_BIET_QUA = {"google": "Tìm trên Google", "google-maps": "Google Maps", "facebook": "Facebook", "zalo": "Zalo",
                "nguoi-quen": "Người quen giới thiệu", "di-ngang-qua": "Đi ngang qua trường", "khac": "Khác"}
TEN_CO_SO = {"kim-ma": "Kim Mã", "chua-lang": "Chùa Láng", "my-dinh": "Mỹ Đình", "ciputra": "Ciputra",
             "chua-chon": "Chưa chọn, nhờ trường tư vấn"}
GIO_VN = timezone(timedelta(hours=7))


def duong_dan() -> Path:
    return Path((os.environ.get("CASA_WEBSITE_DANG_KY") or TEP_MAC_DINH).strip())


def da_cau_hinh() -> bool:
    """Có tệp và đọc được. Tệp chưa có (website chưa nhận đăng ký nào) cũng coi như chưa cấu hình."""
    p = duong_dan()
    return p.is_file() and os.access(p, os.R_OK)


def _ma(h: dict) -> str:
    return hashlib.sha256(f"{h.get('thoi_gian', '')}|{h.get('sdt', '')}".encode()).hexdigest()[:16]


def _gio_vn(iso: str) -> str:
    """"2026-11-27T02:15:00.000Z" (UTC) → "27/11/2026 09:15" (giờ Việt Nam); chuỗi lạ thì giữ nguyên."""
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso or ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(GIO_VN).strftime("%d/%m/%Y %H:%M")


def dong_bo(conn: sqlite3.Connection) -> int | None:
    """Đọc tệp đăng ký vào bảng `website`. Trả số dòng hợp lệ; None khi chưa có tệp hoặc đọc lỗi (giữ dữ liệu cũ).
    Dòng hỏng (JSON lỗi, thiếu SĐT) bỏ qua. Không bao giờ ghi vào tệp của website."""
    if not da_cau_hinh():
        return None
    try:
        dong = duong_dan().read_text(encoding="utf-8").splitlines()
    except OSError as e:
        log.warning("Không đọc được tệp đăng ký website: %s", type(e).__name__)
        db.dat_he_thong(conn, "website_loi", f"{dongho.gio_vn(dongho.bay_gio())}: không đọc được tệp ({type(e).__name__})")
        conn.commit()
        return None
    so = 0
    for s in dong:
        try:
            h = json.loads(s)
        except ValueError:
            continue
        if not isinstance(h, dict) or len(logic.chu_so(str(h.get("sdt") or ""))) < 9:
            continue
        sach = {k: str(v if v is not None else "").strip() for k, v in h.items()}
        conn.execute("INSERT INTO website (ma, du_lieu, thoi_gian) VALUES (?, ?, ?) "
                     "ON CONFLICT(ma) DO UPDATE SET du_lieu = excluded.du_lieu",
                     (_ma(sach), json.dumps(sach, ensure_ascii=False), sach.get("thoi_gian", "")))
        so += 1
    db.dat_he_thong(conn, "website_lay_luc", dongho.ghi_gio(dongho.bay_gio()))
    db.dat_he_thong(conn, "website_loi", "")
    conn.commit()
    return so


def _hang(r: sqlite3.Row) -> dict:
    h = json.loads(r["du_lieu"])
    h["ma"] = r["ma"]
    h["gio_vn"] = _gio_vn(h.get("thoi_gian", ""))
    h["ten_co_so"] = TEN_CO_SO.get(h.get("co_so", ""), h.get("co_so", ""))
    h["ten_biet_qua"] = TEN_BIET_QUA.get(h.get("biet_qua", ""), "")
    h["sinh"] = _sinh(h)
    return h


def _sinh(h: dict) -> str:
    t, n = h.get("thang_sinh", ""), h.get("nam_sinh", "")
    return f"{t}/{n}" if t and n else ""


def chua_nhan(conn: sqlite3.Connection, kem_trung: bool = True) -> list[dict]:
    """Đăng ký website chưa có hồ sơ (chưa giao), chưa bị bỏ qua. Mới nhất lên đầu.
    Mỗi hàng: các khóa của dòng JSON + `ma`, `gio_vn`, `ten_co_so`, `ten_biet_qua`, `sinh`, `trung` (khi kem_trung)."""
    da_giao = {r[0] for r in conn.execute("SELECT website_id FROM lead WHERE website_id != ''")}
    theo_so: dict[str, list[sqlite3.Row]] = {}
    if kem_trung:
        for r in conn.execute("SELECT lead.*, nguoi_dung.ten AS ten_sale FROM lead "
                              "LEFT JOIN nguoi_dung ON nguoi_dung.id = lead.sale_id"):
            theo_so.setdefault(logic.chu_so(r["sdt"]), []).append(r)
    kq = []
    for r in conn.execute("SELECT * FROM website WHERE bo_qua = 0 ORDER BY thoi_gian DESC, ma"):
        if r["ma"] in da_giao:
            continue
        h = _hang(r)
        if kem_trung:
            h["trung"] = theo_so.get(logic.chu_so(h.get("sdt", "")), [])
        kq.append(h)
    return kq


def so_chua_nhan(conn: sqlite3.Connection) -> int:
    return len(chua_nhan(conn, kem_trung=False))


def mot_hang(conn: sqlite3.Connection, ma: str) -> dict | None:
    r = conn.execute("SELECT * FROM website WHERE ma = ?", (ma,)).fetchone()
    return _hang(r) if r else None


def dien_san(h: dict, ds_co_so: list[str], ds_nguon: list[str]) -> dict:
    """Giá trị điền sẵn cho biểu mẫu Thêm lead từ một đăng ký website."""
    co_so = CO_SO.get(h.get("co_so", ""), "")
    nguon = NGUON.get(h.get("biet_qua", ""), NGUON_KHONG_CHON)
    ghi = [f"Đăng ký tham quan trên website lúc {h['gio_vn']}"
           + (" (trang tiếng Anh)" if h.get("ngon_ngu") == "en" else "") + "."]
    if h.get("co_so"):
        ghi.append(f"Cơ sở chọn trên form: {h['ten_co_so']}")
    ghi.append(f"Biết Casa qua: {h['ten_biet_qua'] or 'không chọn'}")
    if h.get("nguon"):
        ghi.append(f"Nguồn truy cập: {h['nguon']}")
    return {
        "ten_ph": h.get("ten", ""),
        "sdt": h.get("sdt", ""),
        "tuoi_be": f"sinh tháng {h['sinh']}" if h["sinh"] else "",
        "co_so": co_so if co_so in ds_co_so else "",
        "nguon": nguon if nguon in ds_nguon else "",
        "chien_dich": h.get("nguon", ""),
        "ghi_chu": "\n".join(ghi),
        "website_id": h["ma"],
    }
