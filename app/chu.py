"""Màn của chủ (đợt B): Bỏ quên + Nhắc sale, Rất quan tâm chưa chốt, Theo sale, Gửi ưu đãi / thông tin,
Báo cáo tháng, Cài đặt (số ngày nhắc, ngày nghỉ, danh mục), xuất CSV.

Mọi đường ở đây chỉ chủ vào được (`_chu`). Danh sách gửi ưu đãi / thông tin và phễu tháng dùng thẳng
hàm của bộ quy tắc (`nen_gui_uu_dai`, `nen_gui_thong_tin`, `thong_ke_thang`).
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from . import db, dongho, logic, quy_tac_nhac as q, telegram
from .main import KhongThay, _bieu_mau, _chu, _conn, _ngay_nhap, _nguoi, _ve, _ve_lai

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
        return _ve(request, "chu.html", nguoi, so_bo_quen=so)
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
        conn.execute("UPDATE lead SET chu_nhac_luc = ? WHERE id = ?", (dongho.ghi_gio(dongho.bay_gio()), lead_id))
        conn.commit()
        be = f" (bé {r['ten_be']})" if r["ten_be"] else ""
        tin = [f"{nguoi['ten']} nhắc: liên hệ {r['ten_ph']}{be}, {r['co_so'] or 'chưa rõ cơ sở'}."]
        if lt.so_ngay_qua_han:
            tin.append(f"Quá hạn {lt.so_ngay_qua_han} ngày.")
        if lt.viec:
            tin.append(f"Việc cần làm: {lt.viec}.")
        tin.append(f"Lần cuối: {lt.lan_cuoi_tom_tat}.")
        da_gui = bool(sale) and await run_in_threadpool(telegram.gui_tin, sale["telegram_chat_id"] or "", "\n".join(tin))
        tb = "Đã gửi Telegram nhắc sale." if da_gui else "Đã ghi lại lúc nhắc, nhưng chưa gửi được Telegram (sale chưa nối Telegram hoặc chưa cấu hình bot)."
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
        for s in conn.execute("SELECT * FROM nguoi_dung WHERE dang_lam = 1 ORDER BY vai_tro DESC, ten"):
            cua = [lt for lt in ds if lt.row["sale_id"] == s["id"]]
            if s["vai_tro"] == "chu" and not cua:
                continue
            chot = sum(lt.giai_doan == q.GD_CHOT for lt in cua)
            so_cs = conn.execute("SELECT COUNT(*), SUM(substr(thoi_gian, 1, 10) = ?) FROM cham_soc WHERE sale_id = ?",
                                 (hom_nay.isoformat(), s["id"])).fetchone()
            hang.append(dict(ten=s["ten"], co_so=s["co_so"], tong=len(cua),
                             dang=sum(lt.giai_doan == q.GD_DANG for lt in cua),
                             qua_han=sum(lt.khan == "Quá hạn" for lt in cua), chot=chot,
                             ty_le=f"{chot * 100 // len(cua)}%" if cua else "–",
                             hom_nay=so_cs[1] or 0, so_cs=so_cs[0]))
        return _ve(request, "chu_theo_sale.html", nguoi, hang=hang)
    finally:
        conn.close()


# ------------------------------------------------------------------ gửi ưu đãi, gửi thông tin

def _ds_gui(conn: sqlite3.Connection, nguoi: sqlite3.Row, loai: str, co_so: str) -> list[dict]:
    ch, hom_nay = logic.cau_hinh(conn), dongho.hom_nay()
    gui: dict[int, list[q.LanGui]] = {}
    for g in conn.execute("SELECT lead_id, thoi_gian, loai FROM gui_thong_tin"):
        gui.setdefault(g["lead_id"], []).append(q.LanGui(dongho.doc_gio(g["thoi_gian"]), g["loai"]))
    kq = []
    for lt in _tat_ca(conn, nguoi, co_so):
        g = gui.get(lt.row["id"], [])
        co_sdt = len(logic.chu_so(lt.row["sdt"])) >= 9
        if loai == q.GUI_UU_DAI:
            cuoi = logic.lan_cham_soc(lt.lan_cuoi) if lt.lan_cuoi else None
            hoc_phi = q.bang_khoan_hoc_phi(cuoi, lt.row["ly_do_chat_luong"], [c["phan_hoi"] for c in lt.lich_su])
            lan_cuoi = dongho.doc_gio(lt.lan_cuoi["thoi_gian"] if lt.lan_cuoi else lt.row["ngay_nhan"])
            da_coc = bool(lt.lan_cuoi) and lt.lan_cuoi["tinh_trang"] == q.DAT_COC
            if not q.nen_gui_uu_dai(lt.giai_doan, co_sdt, hoc_phi, lan_cuoi, g, hom_nay, ch, da_coc):
                continue
        else:
            hoc_phi = False
            if not q.nen_gui_thong_tin(lt.giai_doan, co_sdt, g, hom_nay, ch):
                continue
        cung_loai = sorted(x.thoi_gian for x in g if x.loai == loai)
        kq.append(dict(lt=lt, hoc_phi=hoc_phi, so_lan=len(cung_loai), lan_cuoi=cung_loai[-1] if cung_loai else None))
    kq.sort(key=lambda x: (not x["hoc_phi"], x["lt"].row["co_so"], x["lt"].row["ten_ph"]))
    return kq


LOAI_GUI = {"uu-dai": (q.GUI_UU_DAI, "Gửi ưu đãi"), "thong-tin": (q.GUI_THONG_TIN, "Gửi thông tin")}


@router.get("/gui/{kieu}", response_class=HTMLResponse)
def ds_gui(request: Request, kieu: str, co_so: str = "", tb: str = ""):
    if kieu not in LOAI_GUI:
        raise KhongThay()
    loai, tieu_de = LOAI_GUI[kieu]
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        return _ve(request, "chu_gui.html", nguoi, ds=_ds_gui(conn, nguoi, loai, co_so), kieu=kieu, loai=loai,
                   tieu_de=tieu_de, co_so=co_so, ds_co_so=db.danh_muc(conn, "Cơ sở"), tb=tb)
    finally:
        conn.close()


@router.post("/gui/{kieu}")
async def da_gui(request: Request, kieu: str):
    if kieu not in LOAI_GUI:
        raise KhongThay()
    loai, _ = LOAI_GUI[kieu]
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ids = [int(x) for x in form.getlist("lead_id") if x.isdigit()]
        bay_gio = dongho.ghi_gio(dongho.bay_gio())
        so = 0
        for i in ids:
            if logic.mot_lead(conn, nguoi, i) is not None:
                conn.execute("INSERT INTO gui_thong_tin (lead_id, thoi_gian, loai, nguoi_gui) VALUES (?, ?, ?, ?)",
                             (i, bay_gio, loai, nguoi["id"]))
                so += 1
        conn.commit()
        tb = f"Đã ghi {so} phụ huynh đã gửi." if so else "Chưa chọn phụ huynh nào."
        return _ve_lai(f"/chu/gui/{kieu}?{urlencode({'tb': tb, 'co_so': form.get('co_so') or ''})}")
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
        dem = q.thong_ke_thang(ho_so, cs, thang, co_so)
        truoc = q.thong_ke_thang(ho_so, cs, _thang_truoc(thang), co_so)
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

@router.get("/cai-dat", response_class=HTMLResponse)
def cai_dat(request: Request, tb: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        return _ve(request, "chu_cai_dat.html", nguoi, tb=tb,
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
            sai = []
            for r in conn.execute("SELECT khoa FROM cau_hinh").fetchall():
                v = (form.get("ch_" + r["khoa"]) or "").strip()
                if v.isdigit() and 0 <= int(v) <= 1000:
                    conn.execute("UPDATE cau_hinh SET gia_tri = ? WHERE khoa = ?", (int(v), r["khoa"]))
                elif v:
                    sai.append(r["khoa"])
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
        elif viec == "bo_danh_muc" and form.get("loai") in db.LOAI_DANH_MUC:
            conn.execute("DELETE FROM danh_muc WHERE loai = ? AND gia_tri = ?", (form.get("loai"), form.get("gia_tri") or ""))
            tb = "Đã bỏ lựa chọn (lead cũ đã chọn giá trị này vẫn giữ nguyên)."
        conn.commit()
        return _ve_lai("/chu/cai-dat?" + urlencode({"tb": tb}))
    finally:
        conn.close()


# ------------------------------------------------------------------ xuất CSV

@router.get("/xuat/{ten}.csv")
def xuat(request: Request, ten: str):
    """Hai tệp cùng tên cột như Sheet cũ, để báo cáo tuần (plugin casa-ops) đọc được."""
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ten_sale = {r["id"]: r["ten_dang_nhap"] for r in conn.execute("SELECT id, ten_dang_nhap FROM nguoi_dung")}
        out = io.StringIO()
        w = csv.writer(out)
        if ten == "ho-so-lead":
            w.writerow(q.COT_HO_SO)
            for r in conn.execute("SELECT * FROM lead ORDER BY id"):
                w.writerow([r["id"], r["ngay_nhan"], r["ten_ph"], r["ten_be"], r["tuoi_be"], r["sdt"], r["co_so"],
                            r["nguon"], r["chien_dich"], r["ph_quan_tam"], ten_sale.get(r["sale_id"], ""),
                            r["customer_id"], r["chat_luong"], r["ly_do_chat_luong"], r["ghi_chu"],
                            "TRUE" if r["tam_dung"] else "FALSE", r["chu_nhac_luc"] or "", r["ngay_sinh_be"] or "",
                            r["em_nho"], r["ngay_sinh_em"] or ""])
        elif ten == "cham-soc":
            w.writerow(q.COT_CHAM_SOC)
            for r in conn.execute("SELECT * FROM cham_soc ORDER BY thoi_gian, id"):
                han = logic.ngay_hen(r)
                w.writerow([r["id"], r["lead_id"], r["thoi_gian"], ten_sale.get(r["sale_id"], ""), r["phuong_thuc"],
                            r["tinh_trang"], r["muc_quan_tam"], r["phan_hoi"], r["ly_do_tu_choi"],
                            han.isoformat() if han else "", r["ngay_hen_tham_quan"] or "", "", "",
                            "TRUE" if r["ph_chu_dong"] else "FALSE", r["hen_lai_sau"],
                            "TRUE" if r["da_gui_thu_moi"] else "FALSE", r["ngay_nhap_hoc"] or ""])
        else:
            raise KhongThay()
        ngay = dongho.hom_nay().strftime("%Y%m%d")
        return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{ten}-{ngay}.csv"'})
    finally:
        conn.close()
