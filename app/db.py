"""Cơ sở dữ liệu SQLite của app. Một tệp, nằm NGOÀI thư mục mã khi chạy thật (biến CASA_LEAD_DATA).

Lược đồ chỉ thêm, không đổi: cột mới thì thêm bằng `_them_cot` (kiểm tra trước khi ALTER), không
bao giờ DROP. Dữ liệu là tên và SĐT phụ huynh: không ghi vào log, không chép vào kho mã.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import quy_tac_nhac as q
from .dongho import bay_gio, ghi_gio

GOC = Path(__file__).resolve().parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS nguoi_dung (
    id INTEGER PRIMARY KEY,
    ten_dang_nhap TEXT NOT NULL UNIQUE,
    ten TEXT NOT NULL,
    co_so TEXT NOT NULL DEFAULT '',
    vai_tro TEXT NOT NULL CHECK (vai_tro IN ('chu', 'sale')),
    dang_lam INTEGER NOT NULL DEFAULT 1,
    mat_khau TEXT NOT NULL,
    phien INTEGER NOT NULL DEFAULT 0,
    telegram_chat_id TEXT,
    telegram_ma TEXT,
    tao_luc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lead (
    id INTEGER PRIMARY KEY,
    ngay_nhan TEXT NOT NULL,
    ten_ph TEXT NOT NULL,
    ten_be TEXT NOT NULL DEFAULT '',
    tuoi_be TEXT NOT NULL DEFAULT '',
    sdt TEXT NOT NULL,
    co_so TEXT NOT NULL DEFAULT '',
    nguon TEXT NOT NULL DEFAULT '',
    chien_dich TEXT NOT NULL DEFAULT '',
    ph_quan_tam TEXT NOT NULL DEFAULT '',
    sale_id INTEGER REFERENCES nguoi_dung(id),
    customer_id TEXT NOT NULL DEFAULT '',
    chat_luong TEXT NOT NULL DEFAULT '',
    ly_do_chat_luong TEXT NOT NULL DEFAULT '',
    ghi_chu TEXT NOT NULL DEFAULT '',
    tam_dung INTEGER NOT NULL DEFAULT 0,
    chu_nhac_luc TEXT,
    ngay_sinh_be TEXT,
    em_nho TEXT NOT NULL DEFAULT '',
    ngay_sinh_em TEXT,
    tao_boi INTEGER REFERENCES nguoi_dung(id),
    tao_luc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lead_sale ON lead (sale_id);
CREATE INDEX IF NOT EXISTS lead_sdt ON lead (sdt);
CREATE TABLE IF NOT EXISTS cham_soc (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES lead(id),
    thoi_gian TEXT NOT NULL,
    sale_id INTEGER REFERENCES nguoi_dung(id),
    phuong_thuc TEXT NOT NULL DEFAULT '',
    tinh_trang TEXT NOT NULL,
    muc_quan_tam TEXT NOT NULL DEFAULT '',
    phan_hoi TEXT NOT NULL DEFAULT '',
    ly_do_tu_choi TEXT NOT NULL DEFAULT '',
    hen_lai_sau TEXT NOT NULL DEFAULT '',
    ngay_hen_goi_lai TEXT,
    ngay_hen_tham_quan TEXT,
    ph_chu_dong INTEGER NOT NULL DEFAULT 0,
    da_gui_thu_moi INTEGER NOT NULL DEFAULT 0,
    ngay_nhap_hoc TEXT,
    sua_luc TEXT
);
CREATE INDEX IF NOT EXISTS cham_soc_lead ON cham_soc (lead_id, thoi_gian);
CREATE TABLE IF NOT EXISTS danh_muc (
    id INTEGER PRIMARY KEY,
    loai TEXT NOT NULL,
    gia_tri TEXT NOT NULL,
    thu_tu INTEGER NOT NULL DEFAULT 0,
    UNIQUE (loai, gia_tri)
);
CREATE TABLE IF NOT EXISTS cau_hinh (
    khoa TEXT PRIMARY KEY,
    gia_tri INTEGER NOT NULL,
    y_nghia TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ngay_nghi (
    ngay TEXT PRIMARY KEY,
    ten TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS gui_thong_tin (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES lead(id),
    thoi_gian TEXT NOT NULL,
    loai TEXT NOT NULL,
    nguoi_gui INTEGER REFERENCES nguoi_dung(id),
    ghi_chu TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS viec_gui_den (
    lead_id INTEGER NOT NULL REFERENCES lead(id),
    loai TEXT NOT NULL,
    han TEXT NOT NULL,
    PRIMARY KEY (lead_id, loai)
);
CREATE TABLE IF NOT EXISTS messenger (
    customer_id TEXT PRIMARY KEY,
    du_lieu TEXT NOT NULL,
    cap_nhat_sheet TEXT NOT NULL DEFAULT '',
    lay_luc TEXT NOT NULL,
    bo_qua INTEGER NOT NULL DEFAULT 0,
    bo_qua_boi INTEGER REFERENCES nguoi_dung(id),
    bo_qua_luc TEXT
);
CREATE TABLE IF NOT EXISTS he_thong (
    khoa TEXT PRIMARY KEY,
    gia_tri TEXT NOT NULL
);
"""

# Danh mục chủ tự sửa được. Tình trạng, lý do từ chối… cố định trong mã vì quy tắc nhắc dựa vào chúng.
LOAI_DANH_MUC = ["Cơ sở", "Nguồn", "Mối quan tâm", "Lý do chất lượng"]
PHUONG_THUC = ["Gọi điện", "Zalo", "Messenger (Facebook)", "SMS", "Gặp trực tiếp tại trường"]
MUC_QUAN_TAM = ["Rất quan tâm", "Quan tâm bình thường", "Hời hợt"]
CHAT_LUONG = ["Tốt", "Trung bình", "Kém"]


def duong_dan_db() -> Path:
    """Tệp cơ sở dữ liệu. Khi chạy thật (CASA_LEAD_ENV=production) bắt buộc đặt CASA_LEAD_DATA ra NGOÀI
    thư mục mã: thiếu biến thì cron hay lệnh tạo tài khoản sẽ lặng lẽ dùng một cơ sở dữ liệu rỗng khác."""
    bien = os.environ.get("CASA_LEAD_DATA")
    if os.environ.get("CASA_LEAD_ENV") == "production":
        if not bien:
            raise SystemExit("Chạy thật mà chưa đặt CASA_LEAD_DATA (vd /var/lib/casa-lead). Xem docs/TRIEN-KHAI.md.")
        if Path(bien).resolve().is_relative_to(GOC):
            raise SystemExit("CASA_LEAD_DATA đang nằm trong thư mục mã: dữ liệu phụ huynh có thể lọt lên GitHub. "
                             "Đặt ra ngoài, vd /var/lib/casa-lead.")
    return Path(bien or GOC / "data") / "casa-lead.db"


def ket_noi(duong_dan: Path | None = None) -> sqlite3.Connection:
    p = duong_dan or duong_dan_db()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _them_cot(conn: sqlite3.Connection, bang: str, cot: str, kieu: str) -> None:
    """Thêm cột nếu bảng chưa có (lược đồ chỉ thêm)."""
    if cot not in {r[1] for r in conn.execute(f"PRAGMA table_info({bang})")}:
        conn.execute(f"ALTER TABLE {bang} ADD COLUMN {cot} {kieu}")


def khoi_tao(conn: sqlite3.Connection) -> None:
    """Tạo bảng nếu chưa có, điền cấu hình mặc định. Chạy mỗi lần khởi động: không xoá gì."""
    conn.executescript(SCHEMA)
    _them_cot(conn, "cham_soc", "ly_do_chi_tiet", "TEXT NOT NULL DEFAULT ''")  # chi tiết khi lý do từ chối là "Khác"
    _them_cot(conn, "lead", "email", "TEXT NOT NULL DEFAULT ''")  # không bắt buộc; để sale gửi mail
    for khoa, gia_tri in q.CAU_HINH_MAC_DINH.items():
        conn.execute("INSERT OR IGNORE INTO cau_hinh (khoa, gia_tri, y_nghia) VALUES (?, ?, ?)",
                     (khoa, gia_tri, q.Y_NGHIA_CAU_HINH.get(khoa, "")))
        # Ý nghĩa là chữ của app (không phải số chủ đã sửa): cập nhật theo quy tắc hiện tại
        conn.execute("UPDATE cau_hinh SET y_nghia = ? WHERE khoa = ? AND y_nghia != ?",
                     (q.Y_NGHIA_CAU_HINH.get(khoa, ""), khoa, q.Y_NGHIA_CAU_HINH.get(khoa, "")))
    if conn.execute("SELECT COUNT(*) FROM danh_muc").fetchone()[0] == 0:
        for i, (loai, gia_tri) in enumerate(q.DANH_MUC_MAU):
            if loai in LOAI_DANH_MUC:
                conn.execute("INSERT INTO danh_muc (loai, gia_tri, thu_tu) VALUES (?, ?, ?)", (loai, gia_tri, i))
    if conn.execute("SELECT COUNT(*) FROM he_thong WHERE khoa = 'da_dien_ngay_nghi'").fetchone()[0] == 0:
        for ngay, ten in q.NGAY_NGHI_MAU:
            conn.execute("INSERT OR IGNORE INTO ngay_nghi (ngay, ten) VALUES (?, ?)", (ngay.isoformat(), ten))
        conn.execute("INSERT INTO he_thong (khoa, gia_tri) VALUES ('da_dien_ngay_nghi', ?)", (ghi_gio(bay_gio()),))
    conn.commit()


def danh_muc(conn: sqlite3.Connection, loai: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT gia_tri FROM danh_muc WHERE loai = ? ORDER BY thu_tu, id", (loai,))]


def lay_he_thong(conn: sqlite3.Connection, khoa: str, mac_dinh: str = "") -> str:
    r = conn.execute("SELECT gia_tri FROM he_thong WHERE khoa = ?", (khoa,)).fetchone()
    return r[0] if r else mac_dinh


def dat_he_thong(conn: sqlite3.Connection, khoa: str, gia_tri: str) -> None:
    conn.execute("INSERT INTO he_thong (khoa, gia_tri) VALUES (?, ?) "
                 "ON CONFLICT(khoa) DO UPDATE SET gia_tri = excluded.gia_tri", (khoa, gia_tri))
