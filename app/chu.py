"""Màn của chủ (đợt B): Bỏ quên + Nhắc sale, Rất quan tâm chưa chốt, Theo sale, Gửi ưu đãi / thông tin,
Báo cáo tháng, Cài đặt (số ngày nhắc, ngày nghỉ, danh mục), xuất CSV.

Mọi đường ở đây chỉ chủ vào được (`_chu`). Danh sách gửi ưu đãi / thông tin và phễu tháng dùng thẳng
hàm của bộ quy tắc (`han_gui_uu_dai`, `han_gui_thong_tin` qua `logic.viec_gui`, `thong_ke_thang`).
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from . import db, dongho, logic, messenger, quy_tac_nhac as q, telegram
from .main import KhongThay, _bieu_mau, _chu, _conn, _doc_telegram, _ngay_nhap, _nguoi, _ve, _ve_lai

router = APIRouter(prefix="/chu")


def _tat_ca(conn: sqlite3.Connection, nguoi: sqlite3.Row, co_so: str = "") -> list[logic.LeadTinh]:
    return logic.tinh(conn, logic.lead_cua(conn, nguoi, co_so=co_so))


# ------------------------------------------------------------------ trang Quản trị

@router.get("", response_class=HTMLResponse)
def trang_chu(request: Request):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        so = sum(q.bo_quen(lt.giai_doan, lt.khan) for lt in _tat_ca(conn, nguoi))
        return _ve(request, "chu.html", nguoi, so_bo_quen=so, so_messenger=messenger.so_chua_nhan(conn),
                   so_chua_giao=logic.so_chua_giao(conn),
                   messenger_cau_hinh=messenger.da_cau_hinh())
    finally:
        conn.close()


# ------------------------------------------------------------------ lead Messenger chưa nhận

def _dong_bo(bat_buoc: bool) -> None:
    """Gọi Sheet ngoài vòng sự kiện (có thể mất vài giây), bằng kết nối riêng."""
    conn = _conn()
    try:
        messenger.dong_bo(conn) if bat_buoc else messenger.dong_bo_neu_cu(conn)
    finally:
        conn.close()


@router.get("/messenger", response_class=HTMLResponse)
async def ds_messenger(request: Request, tb: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        if messenger.da_cau_hinh():
            await run_in_threadpool(_dong_bo, False)
        lay = db.lay_he_thong(conn, "messenger_lay_luc")
        return _ve(request, "chu_messenger.html", nguoi, ds=messenger.chua_nhan(conn), tb=tb,
                   cau_hinh=messenger.da_cau_hinh(), loi=db.lay_he_thong(conn, "messenger_loi"),
                   lay_luc=dongho.gio_vn(dongho.doc_gio(lay)) if lay else "")
    finally:
        conn.close()


@router.post("/messenger/lay")
async def lay_messenger(request: Request):
    await _bieu_mau(request)
    conn = _conn()
    try:
        _chu(_nguoi(request, conn))
    finally:
        conn.close()
    await run_in_threadpool(_dong_bo, True)
    return _ve_lai("/chu/messenger")


@router.post("/messenger/bo-qua")
async def bo_qua_messenger(request: Request):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        conn.execute("UPDATE messenger SET bo_qua = 1, bo_qua_boi = ?, bo_qua_luc = ? WHERE customer_id = ?",
                     (nguoi["id"], dongho.ghi_gio(dongho.bay_gio()), form.get("customer_id") or ""))
        conn.commit()
        return _ve_lai("/chu/messenger?" + urlencode({"tb": "Đã bỏ qua: phụ huynh này không hiện trong danh sách nữa."}))
    finally:
        conn.close()


# ------------------------------------------------------------------ bỏ quên, nhắc sale

@router.get("/bo-quen", response_class=HTMLResponse)
def bo_quen(request: Request, tb: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ds = [lt for lt in _tat_ca(conn, nguoi) if q.bo_quen(lt.giai_doan, lt.khan)]
        ds.sort(key=lambda lt: (lt.row["ten_sale"] or "", -lt.so_ngay_qua_han))
        return _ve(request, "chu_ds.html", nguoi, ds=ds, tieu_de="Bỏ quên", tb=tb, nhac=True,
                   mo_ta="Lead đang chăm sóc mà đã quá hạn, xếp theo sale. Bấm Nhắc sale để gửi Telegram cho sale phụ trách.")
    finally:
        conn.close()


@router.get("/rat-quan-tam", response_class=HTMLResponse)
def rat_quan_tam(request: Request, tb: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ds = [lt for lt in _tat_ca(conn, nguoi) if lt.lan_cuoi and lt.lan_cuoi["muc_quan_tam"] == "Rất quan tâm"
              and lt.giai_doan not in (q.GD_CHOT, q.GD_DUNG) and lt.lan_cuoi["tinh_trang"] != q.DAT_COC]
        ds.sort(key=lambda lt: (lt.row["ten_sale"] or "", lt.han or date.max))
        return _ve(request, "chu_ds.html", nguoi, ds=ds, tieu_de="Rất quan tâm chưa chốt", tb=tb, nhac=True,
                   mo_ta="Lần liên hệ gần nhất phụ huynh rất quan tâm, nhưng chưa đặt cọc.")
    finally:
        conn.close()


@router.post("/nhac-sale/{lead_id}")
async def nhac_sale(request: Request, lead_id: int):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        r = logic.mot_lead(conn, nguoi, lead_id)
        if r is None:
            raise KhongThay()
        lt = logic.tinh(conn, [r])[0]
        sale = conn.execute("SELECT * FROM nguoi_dung WHERE id = ?", (r["sale_id"],)).fetchone() if r["sale_id"] else None
        if sale is None or sale["dang_lam"]:
            conn.execute("UPDATE lead SET chu_nhac_luc = ? WHERE id = ?", (dongho.ghi_gio(dongho.bay_gio()), lead_id))
            conn.commit()
        be = f" (bé {r['ten_be']})" if r["ten_be"] else ""
        tin = [f"{nguoi['ten']} nhắc: liên hệ {r['ten_ph']}{be}, {r['co_so'] or 'chưa rõ cơ sở'}."]
        if lt.so_ngay_qua_han:
            tin.append(f"Quá hạn {lt.so_ngay_qua_han} ngày.")
        if lt.viec:
            tin.append(f"Việc cần làm: {lt.viec}.")
        tin.append(f"Lần cuối: {lt.lan_cuoi_tom_tat}.")
        if sale is not None and not sale["dang_lam"]:
            tb = f"{sale['ten']} đã nghỉ: không gửi nhắc. Hãy chuyển lead này cho sale khác (Sửa hồ sơ)."
        else:
            da_gui = sale is not None and await run_in_threadpool(telegram.gui_tin, sale["telegram_chat_id"] or "",
                                                                  "\n".join(tin))
            tb = ("Đã gửi Telegram nhắc sale." if da_gui else
                  "Đã ghi lại lúc nhắc, nhưng chưa gửi được Telegram (sale chưa nối Telegram hoặc chưa cấu hình bot).")
        quay_ve = form.get("quay_ve") if form.get("quay_ve") in ("/chu/bo-quen", "/chu/rat-quan-tam") else "/chu/bo-quen"
        return _ve_lai(f"{quay_ve}?{urlencode({'tb': tb})}")
    finally:
        conn.close()


# ------------------------------------------------------------------ theo sale

@router.get("/theo-sale", response_class=HTMLResponse)
def theo_sale(request: Request):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        hom_nay = dongho.hom_nay()
        ds = _tat_ca(conn, nguoi)
        hang = []
        for s in conn.execute("SELECT * FROM nguoi_dung ORDER BY dang_lam DESC, vai_tro DESC, ten"):
            cua = [lt for lt in ds if lt.row["sale_id"] == s["id"]]
            if (s["vai_tro"] == "chu" or not s["dang_lam"]) and not cua:
                continue
            chot = sum(lt.giai_doan == q.GD_CHOT for lt in cua)
            so_cs = conn.execute("SELECT COUNT(*), SUM(substr(thoi_gian, 1, 10) = ?) FROM cham_soc WHERE sale_id = ?",
                                 (hom_nay.isoformat(), s["id"])).fetchone()
            hang.append(dict(ten=s["ten"] + ("" if s["dang_lam"] else " (đã nghỉ)"), co_so=s["co_so"], tong=len(cua),
                             dang=sum(lt.giai_doan == q.GD_DANG for lt in cua),
                             qua_han=sum(lt.khan == "Quá hạn" for lt in cua), chot=chot,
                             ty_le=f"{chot * 100 // len(cua)}%" if cua else "–",
                             hom_nay=so_cs[1] or 0, so_cs=so_cs[0]))
        return _ve(request, "chu_theo_sale.html", nguoi, hang=hang)
    finally:
        conn.close()


# ------------------------------------------------------------------ gửi ưu đãi, gửi thông tin

LOAI_GUI = {"uu-dai": (q.GUI_UU_DAI, "Theo dõi gửi ưu đãi"), "thong-tin": (q.GUI_THONG_TIN, "Theo dõi gửi thông tin")}


@router.get("/gui/{kieu}", response_class=HTMLResponse)
def ds_gui(request: Request, kieu: str, co_so: str = ""):
    """Chủ theo dõi: phụ huynh đã đến hạn nhận ưu đãi / thông tin, sale nào phụ trách, quá hạn bao lâu.
    Sale gửi và bấm Đã gửi ở tab Hôm nay của mình."""
    if kieu not in LOAI_GUI:
        raise KhongThay()
    loai, tieu_de = LOAI_GUI[kieu]
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ds = [v for v in logic.viec_gui(conn, _tat_ca(conn, nguoi, co_so)) if v.loai == loai]
        return _ve(request, "chu_gui.html", nguoi, ds=ds, kieu=kieu, tieu_de=tieu_de, co_so=co_so,
                   ds_co_so=db.danh_muc(conn, "Cơ sở"))
    finally:
        conn.close()


# ------------------------------------------------------------------ báo cáo tháng

def _hang_bao_cao(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    ho_so = [{"Mã lead": str(r["id"]), "Ngày nhận": r["ngay_nhan"], "Cơ sở": r["co_so"]}
             for r in conn.execute("SELECT id, ngay_nhan, co_so FROM lead")]
    cs = [{"Mã lead": str(r["lead_id"]), "Tình trạng": r["tinh_trang"]}
          for r in conn.execute("SELECT lead_id, tinh_trang FROM cham_soc")]
    return ho_so, cs


def _thang_truoc(thang: str) -> str:
    y, m = int(thang[:4]), int(thang[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


@router.get("/bao-cao", response_class=HTMLResponse)
def bao_cao(request: Request, thang: str = "", co_so: str = q.TAT_CA):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        if len(thang) != 7 or thang[4] != "-" or not (thang[:4] + thang[5:]).isdigit():
            thang = dongho.hom_nay().strftime("%Y-%m")
        ho_so, cs = _hang_bao_cao(conn)
        if co_so != q.TAT_CA:  # lead quan tâm nhiều cơ sở được đếm ở mỗi cơ sở đó
            ho_so = [h for h in ho_so if co_so in logic.cac_co_so(h["Cơ sở"])]
        dem = q.thong_ke_thang(ho_so, cs, thang, q.TAT_CA)
        truoc = q.thong_ke_thang(ho_so, cs, _thang_truoc(thang), q.TAT_CA)
        buoc, moi = [], dem[q.BUOC_PHEU[0]]
        for i, b in enumerate(q.BUOC_PHEU):
            tren = dem[q.BUOC_PHEU[i - 1]] if i else None
            buoc.append(dict(ten=b, so=dem[b], so_moi=f"{dem[b] * 100 // moi}%" if moi else "–",
                             so_truoc=(f"{dem[b] * 100 // tren}%" if tren else "–") if i else ""))
        return _ve(request, "chu_bao_cao.html", nguoi, buoc=buoc, thang=thang, co_so=co_so,
                   moi_truoc=truoc[q.BUOC_PHEU[0]], ds_co_so=[q.TAT_CA] + db.danh_muc(conn, "Cơ sở"))
    finally:
        conn.close()


# ------------------------------------------------------------------ cài đặt

THANG_DNH, NGAY_DNH = "Đầu năm học tháng", "Đầu năm học ngày"
# Giới hạn cho từng khoá. Giá trị vô lý (tháng 13, ngày 31/6, tối đa 0 lần) làm bộ quy tắc lỗi hoặc chạy sai
# cho mọi lead, nên từ chối ngay ở đây. Khoá không có trong bảng: số ngày, 0–1000.
GIOI_HAN_CAU_HINH = {THANG_DNH: (1, 12), NGAY_DNH: (1, 31), "Chưa liên lạc tối đa": (1, 20), "Ưu đãi tối đa": (1, 20),
                     "Tuổi nhận học (tháng)": (0, 120), "Tuổi tối đa (tháng)": (1, 120)}


def _ngay_hop_le(thang: int, ngay: int) -> bool:
    try:
        date(2001, thang, ngay)  # năm không nhuận: 29/02 cũng bị từ chối
        return True
    except ValueError:
        return False


@router.get("/cai-dat", response_class=HTMLResponse)
def cai_dat(request: Request, tb: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        return _ve(request, "chu_cai_dat.html", nguoi, tb=tb, tg_cau_hinh=telegram.da_cau_hinh(),
                   nhom=db.lay_he_thong(conn, "telegram_nhom"), nhom_ten=db.lay_he_thong(conn, "telegram_nhom_ten"),
                   nhom_ma=db.lay_he_thong(conn, "telegram_nhom_ma"),
                   cau_hinh=list(conn.execute("SELECT * FROM cau_hinh ORDER BY rowid")),
                   ngay_nghi=list(conn.execute("SELECT * FROM ngay_nghi ORDER BY ngay")),
                   danh_muc={l: db.danh_muc(conn, l) for l in db.LOAI_DANH_MUC})
    finally:
        conn.close()


@router.post("/cai-dat")
async def luu_cai_dat(request: Request):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        viec = form.get("viec")
        tb = "Không làm gì."
        if viec == "cau_hinh":
            cu = logic.cau_hinh(conn)
            moi, sai = dict(cu), []
            for khoa in cu:
                v = (form.get("ch_" + khoa) or "").strip()
                if not v:
                    continue
                tu, den = GIOI_HAN_CAU_HINH.get(khoa, (0, 1000))
                if v.isascii() and v.isdigit() and tu <= int(v) <= den:
                    moi[khoa] = int(v)
                else:
                    sai.append(khoa)
            if not _ngay_hop_le(moi[THANG_DNH], moi[NGAY_DNH]):
                sai += [k for k in (THANG_DNH, NGAY_DNH) if k not in sai]
                moi[THANG_DNH], moi[NGAY_DNH] = cu[THANG_DNH], cu[NGAY_DNH]
            for khoa, v in moi.items():
                if khoa not in sai and v != cu[khoa]:
                    conn.execute("UPDATE cau_hinh SET gia_tri = ? WHERE khoa = ?", (v, khoa))
            tb = "Đã lưu số ngày nhắc." + (f" Bỏ qua ô không hợp lệ: {', '.join(sai)}." if sai else "")
        elif viec == "them_ngay_nghi":
            loi: list[str] = []
            ngay = _ngay_nhap(form, "ngay", loi, "Ngày nghỉ")
            if ngay:
                conn.execute("INSERT OR REPLACE INTO ngay_nghi (ngay, ten) VALUES (?, ?)",
                             (ngay, (form.get("ten") or "").strip()))
                tb = f"Đã thêm ngày nghỉ {dongho.ngay_vn(dongho.doc_ngay(ngay))}."
            else:
                tb = loi[0] if loi else "Chưa nhập ngày."
        elif viec == "bo_ngay_nghi":
            conn.execute("DELETE FROM ngay_nghi WHERE ngay = ?", (form.get("ngay") or "",))
            tb = "Đã bỏ ngày nghỉ."
        elif viec == "them_danh_muc" and form.get("loai") in db.LOAI_DANH_MUC and (form.get("gia_tri") or "").strip():
            conn.execute("INSERT OR IGNORE INTO danh_muc (loai, gia_tri, thu_tu) VALUES (?, ?, "
                         "(SELECT COALESCE(MAX(thu_tu), 0) + 1 FROM danh_muc))", (form.get("loai"), form.get("gia_tri").strip()))
            tb = "Đã thêm lựa chọn."
        elif viec == "noi_nhom":
            telegram.tao_ma_nhom(conn)
            tb = "Làm theo 3 bước ở mục Nhóm Telegram bên dưới."
        elif viec == "kiem_tra_nhom":
            conn.commit()
            await run_in_threadpool(_doc_telegram)
            ten = db.lay_he_thong(conn, "telegram_nhom_ten")
            tb = (f"Đã nối nhóm {ten or 'Telegram'}. Từ sáng mai tin nhắc gửi vào nhóm." if db.lay_he_thong(conn, "telegram_nhom")
                  else "Chưa thấy lệnh trong nhóm. Kiểm tra bot đã ở trong nhóm và lệnh gõ đúng, rồi bấm kiểm tra lại.")
        elif viec == "go_nhom":
            for k in ("telegram_nhom", "telegram_nhom_ten", "telegram_nhom_ma"):
                db.dat_he_thong(conn, k, "")
            tb = "Đã gỡ nhóm. Tin nhắc sáng quay lại gửi riêng cho từng người."
        elif viec == "bo_danh_muc" and form.get("loai") in db.LOAI_DANH_MUC:
            conn.execute("DELETE FROM danh_muc WHERE loai = ? AND gia_tri = ?", (form.get("loai"), form.get("gia_tri") or ""))
            tb = "Đã bỏ lựa chọn (lead cũ đã chọn giá trị này vẫn giữ nguyên)."
        conn.commit()
        return _ve_lai("/chu/cai-dat?" + urlencode({"tb": tb}))
    finally:
        conn.close()


# ------------------------------------------------------------------ xuất CSV

_SO_DIEN_THOAI = re.compile(r"[+\-][\d ().\-]*")


class _BoGhiAnToan:
    """Ô do người gõ (tên, phản hồi, sau này cả tên Facebook) mà bắt đầu bằng = + - @ thì Excel/Sheets chạy như
    công thức. Thêm dấu ' phía trước. SĐT kiểu +84 912 345 678 giữ nguyên."""

    def __init__(self, w):
        self.w = w

    @staticmethod
    def _o(v):
        s = "" if v is None else str(v)
        if s[:1] in ("=", "@", "\t", "\r") or (s[:1] in ("+", "-") and not _SO_DIEN_THOAI.fullmatch(s)):
            return "'" + s
        return s

    def writerow(self, hang):
        self.w.writerow([self._o(v) for v in hang])


@router.get("/xuat/{ten}.csv")
def xuat(request: Request, ten: str):
    """Hai tệp cùng tên cột như Sheet cũ, để báo cáo tuần (plugin casa-ops) đọc được."""
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ten_sale = {r["id"]: r["ten_dang_nhap"] for r in conn.execute("SELECT id, ten_dang_nhap FROM nguoi_dung")}
        out = io.StringIO()
        w = _BoGhiAnToan(csv.writer(out))
        if ten == "ho-so-lead":
            w.writerow(q.COT_HO_SO)
            for r in conn.execute("SELECT * FROM lead ORDER BY id"):
                w.writerow([r["id"], r["ngay_nhan"], r["ten_ph"], r["ten_be"], r["tuoi_be"], r["sdt"], r["co_so"],
                            r["nguon"], r["chien_dich"], r["ph_quan_tam"], ten_sale.get(r["sale_id"], ""),
                            r["customer_id"], r["chat_luong"], r["ly_do_chat_luong"], r["ghi_chu"],
                            "TRUE" if r["tam_dung"] else "FALSE", r["chu_nhac_luc"] or "", r["ngay_sinh_be"] or "",
                            r["em_nho"], r["ngay_sinh_em"] or "", r["email"]])
        elif ten == "cham-soc":
            w.writerow(q.COT_CHAM_SOC)
            ch, nghi = logic.cau_hinh(conn), logic.ngay_nghi(conn)
            rows = list(conn.execute("SELECT * FROM cham_soc ORDER BY thoi_gian, id"))
            cua_lead: dict[int, list[tuple[int, q.LanChamSoc]]] = {}
            for r in rows:
                cua_lead.setdefault(r["lead_id"], []).append((r["id"], logic.lan_cham_soc(r)))
            for r in rows:
                han = logic.ngay_hen(r)
                c = next(x for i, x in cua_lead[r["lead_id"]] if i == r["id"])
                truoc = [x for i, x in cua_lead[r["lead_id"]] if i != r["id"]]
                tiep = q.han_lien_he_tiep(c, truoc, ch, nghi)
                w.writerow([r["id"], r["lead_id"], r["thoi_gian"], ten_sale.get(r["sale_id"], ""), r["phuong_thuc"],
                            r["tinh_trang"], r["muc_quan_tam"], r["phan_hoi"],
                            r["ly_do_tu_choi"] + (f": {r['ly_do_chi_tiet']}" if r["ly_do_chi_tiet"] else ""),
                            han.isoformat() if han else "", r["ngay_hen_tham_quan"] or "", q.lan_thu(truoc, c),
                            tiep.isoformat() if tiep else "",
                            "TRUE" if r["ph_chu_dong"] else "FALSE", r["hen_lai_sau"],
                            "TRUE" if r["da_gui_thu_moi"] else "FALSE", r["ngay_nhap_hoc"] or ""])
        else:
            raise KhongThay()
        ngay = dongho.hom_nay().strftime("%Y%m%d")
        return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{ten}-{ngay}.csv"'})
    finally:
        conn.close()
