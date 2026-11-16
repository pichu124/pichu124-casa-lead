"""Lead Messenger: đọc tab `Leads` mà bot Messenger ghi vào Google Sheet, để chủ giao cho sale.

App không đụng Google API: đọc qua chính web app Apps Script mà bot dùng để ghi (repo bot,
docs/google-sheet-leads.md mục 9), body `{"type": "leads_read", "token": LEADS_READ_TOKEN}`. Token đọc
là token RIÊNG, khác token ghi của bot: lộ token của bot không đọc được dữ liệu phụ huynh.

Biến môi trường: LEADS_SHEET_WEBHOOK_URL (URL web app, như của bot), LEADS_READ_TOKEN (bí mật).
Bản sao các hàng nằm trong bảng `messenger` (mỗi Customer ID một hàng). Lead đã giao là lead có
`lead.customer_id` trùng; chủ có thể "bỏ qua" hàng không phải lead thật (spam, nhầm).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import unicodedata

import httpx

from . import db, dongho, logic

log = logging.getLogger("casa_lead.messenger")

NGUON = "Facebook Messenger"
TEN_LA = "khách chưa rõ tên"
CACH_LAN_TU_DONG = 60  # giây: mở màn Messenger nhiều lần liền thì không gọi Sheet lại


class LoiSheet(Exception):
    pass


def da_cau_hinh() -> bool:
    return bool(os.environ.get("LEADS_SHEET_WEBHOOK_URL") and os.environ.get("LEADS_READ_TOKEN"))


def _tai() -> list[dict]:
    """Gọi web app, trả các hàng tab Leads (khóa như COLUMNS của script). Lỗi thì ném LoiSheet."""
    try:
        r = httpx.post(os.environ["LEADS_SHEET_WEBHOOK_URL"],
                       json={"type": "leads_read", "token": os.environ["LEADS_READ_TOKEN"]},
                       follow_redirects=True, timeout=30)
    except httpx.HTTPError as e:
        raise LoiSheet(f"Không gọi được Sheet ({type(e).__name__})") from None
    if r.status_code != 200:
        raise LoiSheet(f"Sheet trả mã {r.status_code}")
    try:
        body = r.json()
    except ValueError:
        raise LoiSheet("Sheet không trả JSON (sai URL web app?)") from None
    if not isinstance(body, dict) or body.get("ok") is not True or not isinstance(body.get("rows"), list):
        raise LoiSheet("Sheet trả ok:false: sai LEADS_READ_TOKEN, hoặc web app còn chạy bản script cũ")
    return [h for h in body["rows"] if isinstance(h, dict)]


def dong_bo(conn: sqlite3.Connection) -> int | None:
    """Lấy tab Leads về bảng `messenger`. Trả số hàng đã nhận; None khi chưa cấu hình hoặc lỗi (giữ dữ liệu cũ)."""
    if not da_cau_hinh():
        return None
    bay_gio = dongho.ghi_gio(dongho.bay_gio())
    try:
        hang = _tai()
    except LoiSheet as e:
        log.warning("Không đọc được tab Leads: %s", e)
        db.dat_he_thong(conn, "messenger_loi", f"{dongho.gio_vn(dongho.bay_gio())}: {e}")
        conn.commit()
        return None
    so = 0
    for h in hang:
        cid = str(h.get("customer_id") or "").strip().lstrip("'")
        if not cid:
            continue
        sach = {k: str(v if v is not None else "").strip().lstrip("'") for k, v in h.items()}
        conn.execute("INSERT INTO messenger (customer_id, du_lieu, cap_nhat_sheet, lay_luc) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(customer_id) DO UPDATE SET du_lieu = excluded.du_lieu, "
                     "cap_nhat_sheet = excluded.cap_nhat_sheet, lay_luc = excluded.lay_luc",
                     (cid, json.dumps(sach, ensure_ascii=False), sach.get("updated_at") or sach.get("time") or "", bay_gio))
        so += 1
    db.dat_he_thong(conn, "messenger_lay_luc", bay_gio)
    db.dat_he_thong(conn, "messenger_loi", "")
    conn.commit()
    return so


def dong_bo_neu_cu(conn: sqlite3.Connection) -> None:
    """Đồng bộ nếu lần trước đã quá CACH_LAN_TU_DONG giây (mở màn Messenger)."""
    truoc = db.lay_he_thong(conn, "messenger_lay_luc")
    if truoc and (dongho.bay_gio() - dongho.doc_gio(truoc)).total_seconds() < CACH_LAN_TU_DONG:
        return
    dong_bo(conn)


def chua_nhan(conn: sqlite3.Connection) -> list[dict]:
    """Phụ huynh đã để SĐT cho bot mà chưa có hồ sơ (chưa giao) và chưa bị bỏ qua. Mới cập nhật lên đầu.
    Mỗi hàng: các khóa của tab Leads + `trung` (lead khác cùng SĐT, nếu có)."""
    da_giao = {r[0] for r in conn.execute("SELECT customer_id FROM lead WHERE customer_id != ''")}
    kq = []
    for r in conn.execute("SELECT * FROM messenger WHERE bo_qua = 0 ORDER BY cap_nhat_sheet DESC, customer_id"):
        if r["customer_id"] in da_giao:
            continue
        h = json.loads(r["du_lieu"])
        if len(logic.chu_so(h.get("phone", ""))) < 9:
            continue
        h["customer_id"] = r["customer_id"]
        h["trung"] = logic.lead_trung(conn, h["phone"])
        kq.append(h)
    return kq


def mot_hang(conn: sqlite3.Connection, customer_id: str) -> dict | None:
    r = conn.execute("SELECT du_lieu FROM messenger WHERE customer_id = ?", (customer_id,)).fetchone()
    if r is None:
        return None
    h = json.loads(r[0])
    h["customer_id"] = customer_id
    return h


def _khong_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def doan_co_so(chu: str, ds_co_so: list[str]) -> str:
    """"Cơ sở Mỹ Đình - hệ song ngữ" → "Mỹ Đình" (nếu đúng một cơ sở trong danh mục khớp)."""
    t = _khong_dau(chu)
    khop = [c for c in ds_co_so if _khong_dau(c) in t]
    return khop[0] if len(khop) == 1 else ""


def dien_san(h: dict, ds_co_so: list[str], ds_nguon: list[str]) -> dict:
    """Giá trị điền sẵn cho biểu mẫu Thêm lead từ một hàng Messenger."""
    ghi = []
    lan_dau = h.get("first_contact") or h.get("time") or ""
    if lan_dau:
        try:
            lan_dau = dongho.ngay_vn(dongho.doc_gio(lan_dau))
        except ValueError:
            pass
        ghi.append(f"Từ Messenger, nhắn lần đầu {lan_dau}" + (f" (trang {h['page']})" if h.get("page") else "") + ".")
    for nhan, khoa in (("Cơ sở/hệ quan tâm", "campus"), ("Khu vực", "area"), ("Dự kiến nhập học", "expected_start"),
                       ("Hẹn tham quan/học thử", "visit_request"), ("Giai đoạn trên bot", "stage"),
                       ("Tin cuối", "last_message")):
        if h.get(khoa):
            ghi.append(f"{nhan}: {h[khoa]}")
    ten = h.get("fb_name", "")
    return {
        "ten_ph": "" if ten == TEN_LA else ten,
        "sdt": h.get("phone", ""),
        "ten_be": h.get("kid_name", ""),
        "tuoi_be": h.get("kid_age", ""),
        "co_so": doan_co_so(h.get("campus", ""), ds_co_so),
        "nguon": NGUON if NGUON in ds_nguon else "",
        "chien_dich": h.get("ad_title", ""),
        "ghi_chu": "\n".join(ghi),
        "customer_id": h["customer_id"],
    }
