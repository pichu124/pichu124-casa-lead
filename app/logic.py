"""Nối dữ liệu trong cơ sở dữ liệu với bộ quy tắc nhắc (`quy_tac_nhac.py`).

Không tự tính hạn ở đây: mọi hạn, giai đoạn, việc cần làm đều do `trang_thai_lead` của bộ quy tắc
tính (bộ đã có 77 bài kiểm thử). Tệp này chỉ đổi hàng dữ liệu thành đối tượng của bộ quy tắc.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from . import quy_tac_nhac as q
from .dongho import doc_gio, doc_ngay, hom_nay as _hom_nay

# Tình trạng nào thì ô nào có nghĩa. Máy chủ xoá giá trị ở ô không có nghĩa trước khi lưu, để ô bị ẩn
# mà còn giá trị cũ (lỗi đã gặp ở bản AppSheet) không làm sai lịch nhắc.
KHONG_MUC_QUAN_TAM = {q.TU_CHOI, q.CHUA_LIEN_LAC, q.KHONG_DEN}
KHONG_HEN_LAI = {q.TU_CHOI, q.NHAP_HOC, q.DAT_COC, q.KHONG_DEN}
HEN_LAI_SAU = list(q.HEN_NHANH) + [q.HEN_CHON_NGAY]


def cau_hinh(conn: sqlite3.Connection) -> dict[str, int]:
    ch = dict(q.CAU_HINH_MAC_DINH)
    ch.update({r["khoa"]: int(r["gia_tri"]) for r in conn.execute("SELECT khoa, gia_tri FROM cau_hinh")})
    return ch


def ngay_nghi(conn: sqlite3.Connection) -> set[date]:
    return {date.fromisoformat(r[0]) for r in conn.execute("SELECT ngay FROM ngay_nghi")}


def chu_so(sdt: str) -> str:
    """SĐT về dạng so khớp được: chỉ chữ số, +84/84 đầu thành 0."""
    so = re.sub(r"\D", "", sdt or "")
    if so.startswith("84") and len(so) >= 11:
        so = "0" + so[2:]
    return so


def ngay_hen(row: sqlite3.Row) -> date | None:
    """Ngày phụ huynh hẹn gọi lại, như cột "Ngày hẹn" của bản AppSheet."""
    hen = row["hen_lai_sau"] or ""
    if hen in q.HEN_NHANH:
        return q.ngay_hen_nhanh(hen, doc_gio(row["thoi_gian"]).date())
    return doc_ngay(row["ngay_hen_goi_lai"])


def lan_cham_soc(row: sqlite3.Row) -> q.LanChamSoc:
    return q.LanChamSoc(
        thoi_gian=doc_gio(row["thoi_gian"]),
        tinh_trang=row["tinh_trang"],
        ngay_hen_goi_lai=ngay_hen(row),
        ngay_hen_tham_quan=doc_ngay(row["ngay_hen_tham_quan"]),
        ly_do_tu_choi=row["ly_do_tu_choi"] or "",
        ph_chu_dong=bool(row["ph_chu_dong"]),
        da_gui_thu_moi=bool(row["da_gui_thu_moi"]),
        ngay_nhap_hoc=doc_ngay(row["ngay_nhap_hoc"]),
    )


def lead_qt(row: sqlite3.Row) -> q.Lead:
    return q.Lead(
        ngay_nhan=doc_gio(row["ngay_nhan"]),
        tuoi_be=row["tuoi_be"] or "",
        ngay_sinh=doc_ngay(row["ngay_sinh_be"]),
        nguon=row["nguon"] or "",
        tam_dung=bool(row["tam_dung"]),
        em_nho=row["em_nho"] or "",
    )


@dataclass
class LeadTinh:
    """Một lead kèm những gì app tính ra cho nó."""
    row: sqlite3.Row
    han: date | None
    giai_doan: str
    viec: str
    khan: str
    nhom: str
    lan_cuoi: sqlite3.Row | None
    lich_su: list[sqlite3.Row]
    ngay_sinh: date | None
    du_tuoi: date | None
    so_ngay_qua_han: int

    @property
    def tinh_trang_hien_tai(self) -> str:
        return self.lan_cuoi["tinh_trang"] if self.lan_cuoi else "Mới"

    @property
    def lan_cuoi_tom_tat(self) -> str:
        if not self.lan_cuoi:
            return "Chưa liên hệ lần nào"
        tg = doc_gio(self.lan_cuoi["thoi_gian"])
        s = f"{tg:%d/%m} · {self.lan_cuoi['tinh_trang']}"
        if self.lan_cuoi["phan_hoi"]:
            s += " · " + self.lan_cuoi["phan_hoi"]
        return s


def nhom(khan: str, giai_doan: str) -> str:
    """Nhóm ở màn Của tôi: lead dài hạn có hạn còn xa không lẫn vào "Sắp tới"."""
    if khan == "Quá hạn":
        return "1 · Quá hạn"
    if khan == "Hôm nay":
        return "2 · Hôm nay"
    if khan == "Sắp tới" and giai_doan == q.GD_DANG:
        return "3 · Sắp tới"
    return "4 · " + giai_doan


def tinh(conn: sqlite3.Connection, leads: list[sqlite3.Row], hom_nay: date | None = None) -> list[LeadTinh]:
    hom_nay = hom_nay or _hom_nay()
    if not leads:
        return []
    ch, nghi = cau_hinh(conn), ngay_nghi(conn)
    ids = [r["id"] for r in leads]
    cs: dict[int, list[sqlite3.Row]] = {i: [] for i in ids}
    cho = ",".join("?" * len(ids))
    for r in conn.execute(f"SELECT * FROM cham_soc WHERE lead_id IN ({cho}) ORDER BY thoi_gian, id", ids):
        cs[r["lead_id"]].append(r)
    kq = []
    for row in leads:
        lich = cs[row["id"]]
        lead = lead_qt(row)
        tt = q.trang_thai_lead(lead, [lan_cham_soc(c) for c in lich], hom_nay, ch, nghi)
        khan = q.muc_khan(tt.han, hom_nay)
        sinh = lead.ngay_sinh or q.ngay_sinh_uoc_tinh(lead.tuoi_be, lead.ngay_nhan.date())
        du_tuoi = q.cong_thang(sinh, ch["Tuổi nhận học (tháng)"]) if sinh else None
        kq.append(LeadTinh(
            row=row, han=tt.han, giai_doan=tt.giai_doan, viec=tt.viec, khan=khan, nhom=nhom(khan, tt.giai_doan),
            lan_cuoi=lich[-1] if lich else None, lich_su=lich, ngay_sinh=sinh, du_tuoi=du_tuoi,
            so_ngay_qua_han=(hom_nay - tt.han).days if khan == "Quá hạn" else 0,
        ))
    return kq


def cac_co_so(s: str | None) -> list[str]:
    """"Chùa Láng, Kim Mã" → ["Chùa Láng", "Kim Mã"]. Lead có thể quan tâm nhiều cơ sở, hoặc chưa rõ (rỗng)."""
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def so_chua_giao(conn: sqlite3.Connection) -> int:
    """Lead chưa có sale phụ trách (trừ lead chủ đã tạm dừng)."""
    return conn.execute("SELECT COUNT(*) FROM lead WHERE sale_id IS NULL AND tam_dung = 0").fetchone()[0]


def lead_cua(conn: sqlite3.Connection, nguoi: sqlite3.Row, sale_id: int | None = None,
             co_so: str = "") -> list[sqlite3.Row]:
    """Lead người này được thấy: sale chỉ thấy lead mình phụ trách, chủ thấy tất cả (lọc được)."""
    sql = ("SELECT lead.*, nguoi_dung.ten AS ten_sale, nguoi_dung.dang_lam AS sale_dang_lam FROM lead "
           "LEFT JOIN nguoi_dung ON nguoi_dung.id = lead.sale_id WHERE 1 = 1")
    tham: list = []
    if nguoi["vai_tro"] != "chu":
        sql += " AND lead.sale_id = ?"
        tham.append(nguoi["id"])
    elif sale_id:
        sql += " AND lead.sale_id = ?"
        tham.append(sale_id)
    if co_so:  # lead quan tâm nhiều cơ sở thì có mặt ở mỗi cơ sở đó
        sql += " AND (', ' || lead.co_so || ', ') LIKE ?"
        tham.append(f"%, {co_so}, %")
    return list(conn.execute(sql + " ORDER BY lead.ngay_nhan DESC, lead.id DESC", tham))


def mot_lead(conn: sqlite3.Connection, nguoi: sqlite3.Row, lead_id: int) -> sqlite3.Row | None:
    """Một lead, hoặc None nếu không có hay người này không được xem (không phân biệt hai trường hợp)."""
    r = conn.execute("SELECT lead.*, nguoi_dung.ten AS ten_sale FROM lead "
                     "LEFT JOIN nguoi_dung ON nguoi_dung.id = lead.sale_id WHERE lead.id = ?", (lead_id,)).fetchone()
    if r is None or (nguoi["vai_tro"] != "chu" and r["sale_id"] != nguoi["id"]):
        return None
    return r


def lead_trung(conn: sqlite3.Connection, sdt: str, tru_id: int | None = None) -> list[sqlite3.Row]:
    so = chu_so(sdt)
    if len(so) < 9:
        return []
    kq = []
    for r in conn.execute("SELECT lead.*, nguoi_dung.ten AS ten_sale FROM lead "
                          "LEFT JOIN nguoi_dung ON nguoi_dung.id = lead.sale_id"):
        if r["id"] != tru_id and chu_so(r["sdt"]) == so:
            kq.append(r)
    return kq


def co_lead_em(conn: sqlite3.Connection, lead: sqlite3.Row) -> bool:
    return any(r["nguon"] == q.NGUON_EM_NHO for r in lead_trung(conn, lead["sdt"], tru_id=lead["id"]))
