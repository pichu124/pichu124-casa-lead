"""App web chăm sóc lead: màn hình cho sale (Hôm nay, Của tôi, chi tiết lead, ghi nhận) và cho chủ.

Chạy thử: `uvicorn app.main:app --reload`. Chạy thật: xem docs/TRIEN-KHAI.md.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
import os
import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from . import auth, db, dongho, logic, quy_tac_nhac as q, telegram

log = logging.getLogger("casa_lead")
THU_MUC = Path(__file__).resolve().parent
SAN_XUAT = os.environ.get("CASA_LEAD_ENV") == "production"

@asynccontextmanager
async def _vong_doi(_app):
    conn = db.ket_noi()
    db.khoi_tao(conn)
    conn.close()
    yield


app = FastAPI(title="Casa chăm sóc lead", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_vong_doi)
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.khoa_phien(db.duong_dan_db().parent),
    session_cookie="casa_lead",
    max_age=30 * 24 * 3600,
    same_site="lax",
    https_only=SAN_XUAT,
)
app.mount("/static", StaticFiles(directory=THU_MUC / "static"), name="static")
tpl = Jinja2Templates(directory=THU_MUC / "templates")
tpl.env.globals.update(ngay_vn=dongho.ngay_vn, gio_vn=dongho.gio_vn, doc_gio=dongho.doc_gio,
                       doc_ngay=dongho.doc_ngay, q=q, ten_bot=telegram.ten_bot)


class CanDangNhap(Exception):
    pass


class KhongDuQuyen(Exception):
    pass


class KhongThay(Exception):
    pass


@app.exception_handler(CanDangNhap)
def _can_dang_nhap(request: Request, exc: CanDangNhap):
    return RedirectResponse("/dang-nhap", status_code=303)


@app.exception_handler(KhongDuQuyen)
def _khong_du_quyen(request: Request, exc: KhongDuQuyen):
    return HTMLResponse("<p>Bạn không có quyền làm việc này. <a href='/'>Về trang chính</a></p>", status_code=403)


@app.exception_handler(KhongThay)
def _khong_thay(request: Request, exc: KhongThay):
    return HTMLResponse("<p>Không tìm thấy, hoặc bạn không phụ trách lead này. <a href='/'>Về trang chính</a></p>",
                        status_code=404)


# ------------------------------------------------------------------ tiện ích

def _conn() -> sqlite3.Connection:
    return db.ket_noi()


def _nguoi(request: Request, conn: sqlite3.Connection) -> sqlite3.Row:
    uid = request.session.get("uid")
    if not uid:
        raise CanDangNhap()
    r = conn.execute("SELECT * FROM nguoi_dung WHERE id = ?", (uid,)).fetchone()
    if r is None or not r["dang_lam"] or r["phien"] != request.session.get("phien"):
        request.session.clear()
        raise CanDangNhap()
    return r


def _chu(nguoi: sqlite3.Row) -> None:
    if nguoi["vai_tro"] != "chu":
        raise KhongDuQuyen()


async def _bieu_mau(request: Request):
    form = await request.form()
    if not auth.dung_ma_bieu_mau(request.session, form.get("csrf")):
        raise KhongDuQuyen()
    return form


def _ve(request: Request, ten: str, nguoi: sqlite3.Row | None = None, status_code: int = 200, **ctx):
    ctx.update(request=request, nguoi=nguoi, csrf=auth.ma_bieu_mau(request.session))
    return tpl.TemplateResponse(request, ten, ctx, status_code=status_code)


def _ve_lai(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _chu_nhan(form, ten: str) -> str:
    return (form.get(ten) or "").strip()


NAM_HOP_LE = range(2000, 2101)


def _ngay_nhap(form, ten: str, loi: list[str] | None = None, nhan: str = "Ngày") -> str | None:
    """Ngày từ biểu mẫu. Ngày không đọc được hoặc ngoài năm 2000–2100 thì báo lỗi (một ngày vô lý
    như 9999-12-31 làm bộ quy tắc tràn số và hỏng màn hình của mọi người)."""
    s = _chu_nhan(form, ten)
    if not s:
        return None
    try:
        d = dongho.doc_ngay(s)
    except ValueError:
        d = None
    if d is None or d.year not in NAM_HOP_LE:
        if loi is not None:
            loi.append(f"{nhan} không hợp lệ: nhập ngày trong khoảng năm 2000 đến 2100.")
        return None
    return d.isoformat()


# ------------------------------------------------------------------ đăng nhập

@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz():
    conn = _conn()
    try:
        conn.execute("SELECT 1").fetchone()
    finally:
        conn.close()
    return PlainTextResponse("ok")


@app.get("/dang-nhap", response_class=HTMLResponse)
def dang_nhap_trang(request: Request):
    return _ve(request, "dang_nhap.html", loi="")


@app.post("/dang-nhap")
async def dang_nhap(request: Request):
    form = await _bieu_mau(request)
    ten, mk = _chu_nhan(form, "ten_dang_nhap").lower(), form.get("mat_khau") or ""
    if auth.bi_khoa(ten):
        return _ve(request, "dang_nhap.html", loi="Sai quá nhiều lần. Chờ 15 phút rồi thử lại, hoặc nhờ chủ đặt lại mật khẩu.",
                   status_code=429)
    conn = _conn()
    try:
        r = conn.execute("SELECT * FROM nguoi_dung WHERE ten_dang_nhap = ?", (ten,)).fetchone()
    finally:
        conn.close()
    if r is None or not r["dang_lam"] or not auth.dung_mat_khau(mk, r["mat_khau"]):
        auth.ghi_sai(ten)
        return _ve(request, "dang_nhap.html", loi="Sai tên đăng nhập hoặc mật khẩu.", status_code=401)
    auth.xoa_sai(ten)
    request.session.clear()
    request.session.update(uid=r["id"], phien=r["phien"])
    return _ve_lai("/")


@app.post("/dang-xuat")
async def dang_xuat(request: Request):
    await _bieu_mau(request)
    request.session.clear()
    return _ve_lai("/dang-nhap")


# ------------------------------------------------------------------ màn của sale

@app.get("/")
def trang_chu():
    return _ve_lai("/hom-nay")


@app.get("/hom-nay", response_class=HTMLResponse)
def hom_nay(request: Request):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        ds = [lt for lt in logic.tinh(conn, logic.lead_cua(conn, nguoi, sale_id=nguoi["id"]))
              if lt.khan in ("Quá hạn", "Hôm nay")]
        ds.sort(key=lambda lt: (lt.han, lt.row["id"]))
        return _ve(request, "hom_nay.html", nguoi, ds=ds, hom_nay=dongho.hom_nay())
    finally:
        conn.close()


def _loc(ds: list[logic.LeadTinh], tim: str) -> list[logic.LeadTinh]:
    if not tim:
        return ds
    t, so = tim.lower(), logic.chu_so(tim)
    return [lt for lt in ds if t in (lt.row["ten_ph"] or "").lower() or t in (lt.row["ten_be"] or "").lower()
            or (len(so) >= 3 and so in logic.chu_so(lt.row["sdt"]))]


def _nhom(ds: list[logic.LeadTinh]) -> list[tuple[str, list[logic.LeadTinh]]]:
    g: dict[str, list[logic.LeadTinh]] = {}
    for lt in ds:
        g.setdefault(lt.nhom, []).append(lt)
    for v in g.values():
        v.sort(key=lambda lt: (lt.han is None, lt.han or date.min, lt.row["id"]))
    return sorted(g.items())


@app.get("/cua-toi", response_class=HTMLResponse)
def cua_toi(request: Request, tim: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        ds = _loc(logic.tinh(conn, logic.lead_cua(conn, nguoi, sale_id=nguoi["id"])), tim.strip())
        return _ve(request, "danh_sach.html", nguoi, nhom=_nhom(ds), tim=tim, tieu_de="Của tôi",
                   duong_dan="/cua-toi", tong=len(ds))
    finally:
        conn.close()


@app.get("/tat-ca", response_class=HTMLResponse)
def tat_ca(request: Request, tim: str = "", sale: int = 0, co_so: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ds = _loc(logic.tinh(conn, logic.lead_cua(conn, nguoi, sale_id=sale or None, co_so=co_so)), tim.strip())
        ds_sale = list(conn.execute("SELECT id, ten FROM nguoi_dung WHERE dang_lam = 1 ORDER BY ten"))
        return _ve(request, "danh_sach.html", nguoi, nhom=_nhom(ds), tim=tim, tieu_de="Tất cả lead",
                   duong_dan="/tat-ca", tong=len(ds), ds_sale=ds_sale, sale=sale, co_so=co_so,
                   ds_co_so=db.danh_muc(conn, "Cơ sở"))
    finally:
        conn.close()


@app.get("/lead/{lead_id}", response_class=HTMLResponse)
def chi_tiet(request: Request, lead_id: int):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        r = logic.mot_lead(conn, nguoi, lead_id)
        if r is None:
            raise KhongThay()
        lt = logic.tinh(conn, [r])[0]
        ten_sale = {x["id"]: x["ten"] for x in conn.execute("SELECT id, ten FROM nguoi_dung")}
        hien_tao_em = (r["em_nho"] in ("Có em nhỏ", "Sắp sinh em") and r["ngay_sinh_em"]
                       and not logic.co_lead_em(conn, r))
        hien_thu_moi = bool(lt.lan_cuoi) and lt.lan_cuoi["tinh_trang"] == q.DAT_COC and not lt.lan_cuoi["da_gui_thu_moi"]
        return _ve(request, "lead.html", nguoi, lt=lt, r=r, ten_sale=ten_sale, hien_tao_em=hien_tao_em,
                   hien_thu_moi=hien_thu_moi, zalo="https://zalo.me/" + logic.chu_so(r["sdt"]),
                   co_the_sua_cs=lambda c: nguoi["vai_tro"] == "chu" or c["sale_id"] == nguoi["id"])
    finally:
        conn.close()


# ------------------------------------------------------------------ thêm / sửa lead

def _gia_tri_lead(form, nguoi: sqlite3.Row, cu: sqlite3.Row | None) -> tuple[dict, list[str]]:
    v = {k: _chu_nhan(form, k) for k in ("ten_ph", "sdt", "ten_be", "tuoi_be", "co_so", "nguon", "chien_dich",
                                         "chat_luong", "ly_do_chat_luong", "ghi_chu", "em_nho")}
    v["ph_quan_tam"] = ", ".join(x for x in form.getlist("ph_quan_tam") if x)
    loi: list[str] = []
    v["ngay_sinh_be"] = _ngay_nhap(form, "ngay_sinh_be", loi, "Ngày sinh bé")
    loi_em: list[str] = []  # chỉ báo khi ô ngày sinh em đang hiện (Có em nhỏ / Sắp sinh em)
    v["ngay_sinh_em"] = _ngay_nhap(form, "ngay_sinh_em", loi_em, "Ngày sinh của em")
    if not v["ten_ph"]:
        loi.append("Chưa nhập tên phụ huynh.")
    if len(logic.chu_so(v["sdt"])) < 9:
        loi.append("SĐT chưa đúng (cần ít nhất 9 chữ số).")
    if v["chat_luong"] not in ("Trung bình", "Kém"):
        v["ly_do_chat_luong"] = ""
    if v["em_nho"] not in q.EM_NHO:
        v["em_nho"] = ""
    if v["em_nho"] in ("Có em nhỏ", "Sắp sinh em"):
        loi += loi_em
        if not v["ngay_sinh_em"] and not _chu_nhan(form, "ngay_sinh_em"):
            loi.append("Chưa nhập ngày sinh (hoặc dự sinh) của em.")
    else:
        v["ngay_sinh_em"] = None
    if nguoi["vai_tro"] == "chu":
        sale = _chu_nhan(form, "sale_id")
        v["sale_id"] = int(sale) if sale.isdigit() else None
        v["tam_dung"] = 1 if form.get("tam_dung") else 0
    else:  # sale không đổi được người phụ trách và Tạm dừng, kể cả khi sửa tay biểu mẫu
        v["sale_id"] = cu["sale_id"] if cu else nguoi["id"]
        v["tam_dung"] = cu["tam_dung"] if cu else 0
    return v, loi


def _ve_form_lead(request, conn, nguoi, v, loi, lead_id=None, status_code=200):
    return _ve(request, "lead_form.html", nguoi, v=v, loi=loi, lead_id=lead_id, status_code=status_code,
               ds_co_so=db.danh_muc(conn, "Cơ sở"), ds_nguon=db.danh_muc(conn, "Nguồn"),
               ds_quan_tam=db.danh_muc(conn, "Mối quan tâm"), ds_ly_do_cl=db.danh_muc(conn, "Lý do chất lượng"),
               ds_chat_luong=db.CHAT_LUONG,
               # gồm cả sale đang phụ trách dù đã nghỉ, để lưu biểu mẫu không lặng lẽ bỏ giao lead
               ds_sale=list(conn.execute("SELECT id, ten, dang_lam FROM nguoi_dung WHERE dang_lam = 1 OR id = ? "
                                         "ORDER BY dang_lam DESC, ten", (v.get("sale_id"),))))


@app.get("/lead-moi", response_class=HTMLResponse)
def lead_moi_trang(request: Request, em_cua: int = 0):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        v = {"sale_id": nguoi["id"], "tam_dung": 0}
        if em_cua:
            anh = logic.mot_lead(conn, nguoi, em_cua)
            if anh is None:
                raise KhongThay()
            v.update(ten_ph=anh["ten_ph"], sdt=anh["sdt"], co_so=anh["co_so"], nguon=q.NGUON_EM_NHO,
                     ngay_sinh_be=anh["ngay_sinh_em"], sale_id=anh["sale_id"],
                     ghi_chu=f"Em của {anh['ten_be'] or 'bé'} (lead #{anh['id']})")
        return _ve_form_lead(request, conn, nguoi, v, [])
    finally:
        conn.close()


@app.post("/lead-moi")
async def lead_moi(request: Request):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        v, loi = _gia_tri_lead(form, nguoi, None)
        if loi:
            return _ve_form_lead(request, conn, nguoi, v, loi, status_code=400)
        trung = _trung_can_bao(conn, v)
        bay_gio = dongho.ghi_gio(dongho.bay_gio())
        cot = list(v) + ["ngay_nhan", "tao_boi", "tao_luc"]
        cur = conn.execute(f"INSERT INTO lead ({', '.join(cot)}) VALUES ({', '.join('?' * len(cot))})",
                           [*v.values(), bay_gio, nguoi["id"], bay_gio])
        conn.commit()
        if trung:
            await run_in_threadpool(_bao_trung, v, trung)
        if v.get("sale_id") and v["sale_id"] != nguoi["id"]:
            await run_in_threadpool(_bao_duoc_giao, cur.lastrowid, nguoi["ten"])
        return _ve_lai(f"/lead/{cur.lastrowid}")
    finally:
        conn.close()


def _trung_can_bao(conn: sqlite3.Connection, v: dict, tru_id: int | None = None) -> list[sqlite3.Row]:
    """Lead khác cùng SĐT cần báo chủ. Lead em (nguồn Em nhỏ trong gia đình) chỉ bỏ qua lead cùng sale:
    lead của anh/chị tạo bằng nút Tạo lead cho em luôn cùng sale; trùng với lead của sale khác vẫn báo."""
    trung = logic.lead_trung(conn, v["sdt"], tru_id=tru_id)
    if v["nguon"] == q.NGUON_EM_NHO:
        trung = [r for r in trung if r["sale_id"] != v["sale_id"]]
    return trung


def _bao_trung(v: dict, trung: list[sqlite3.Row]) -> None:
    """Báo chủ qua Telegram. Chạy ngoài vòng sự kiện (gọi mạng có thể chậm tới 15 giây)."""
    conn = _conn()
    try:
        ten_sale = {x["id"]: x["ten"] for x in conn.execute("SELECT id, ten FROM nguoi_dung")}
        chu = [r["telegram_chat_id"] or "" for r in
               conn.execute("SELECT telegram_chat_id FROM nguoi_dung WHERE vai_tro = 'chu' AND dang_lam = 1")]
    finally:
        conn.close()
    tin = [f"Lead trùng SĐT: {v['ten_ph']} (sale {ten_sale.get(v['sale_id'], 'chưa giao')}) vừa được thêm, "
           f"trùng số với:"]
    tin += [f"- {r['ten_ph']} · sale {r['ten_sale'] or 'chưa giao'} · {r['co_so'] or 'chưa rõ cơ sở'}" for r in trung]
    tin.append("Mở app, mục Tất cả lead, để gộp hoặc giao lại.")
    for chat in chu:
        telegram.gui_tin(chat, "\n".join(tin))


def _bao_duoc_giao(lead_id: int, nguoi_giao: str) -> None:
    """Báo sale qua Telegram khi chủ giao (hoặc chuyển) một lead cho họ. Không kèm SĐT."""
    conn = _conn()
    try:
        r = conn.execute("SELECT lead.*, nguoi_dung.telegram_chat_id AS chat FROM lead "
                         "JOIN nguoi_dung ON nguoi_dung.id = lead.sale_id WHERE lead.id = ? AND nguoi_dung.dang_lam = 1",
                         (lead_id,)).fetchone()
    finally:
        conn.close()
    if r is None:
        return
    be = f" (bé {r['ten_be']})" if r["ten_be"] else ""
    tin = [f"{nguoi_giao} vừa giao cho bạn lead {r['ten_ph']}{be}, {r['co_so'] or 'chưa rõ cơ sở'}."]
    if r["nguon"]:
        tin.append(f"Nguồn: {r['nguon']}.")
    tin.append("Mở app, mục Hôm nay, để liên hệ.")
    telegram.gui_tin(r["chat"] or "", "\n".join(tin))


@app.get("/lead/{lead_id}/sua", response_class=HTMLResponse)
def sua_lead_trang(request: Request, lead_id: int):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        r = logic.mot_lead(conn, nguoi, lead_id)
        if r is None:
            raise KhongThay()
        return _ve_form_lead(request, conn, nguoi, dict(r), [], lead_id=lead_id)
    finally:
        conn.close()


@app.post("/lead/{lead_id}/sua")
async def sua_lead(request: Request, lead_id: int):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        cu = logic.mot_lead(conn, nguoi, lead_id)
        if cu is None:
            raise KhongThay()
        v, loi = _gia_tri_lead(form, nguoi, cu)
        if loi:
            return _ve_form_lead(request, conn, nguoi, v, loi, lead_id=lead_id, status_code=400)
        trung = (_trung_can_bao(conn, v, tru_id=lead_id)
                 if logic.chu_so(v["sdt"]) != logic.chu_so(cu["sdt"]) else [])
        conn.execute(f"UPDATE lead SET {', '.join(k + ' = ?' for k in v)} WHERE id = ?", [*v.values(), lead_id])
        conn.commit()
        if trung:
            await run_in_threadpool(_bao_trung, v, trung)
        if v.get("sale_id") and v["sale_id"] != cu["sale_id"] and v["sale_id"] != nguoi["id"]:
            await run_in_threadpool(_bao_duoc_giao, lead_id, nguoi["ten"])
        return _ve_lai(f"/lead/{lead_id}")
    finally:
        conn.close()


# ------------------------------------------------------------------ ghi nhận lần chăm sóc

def _gia_tri_cham_soc(form) -> tuple[dict, list[str]]:
    v = {k: _chu_nhan(form, k) for k in ("phuong_thuc", "tinh_trang", "muc_quan_tam", "phan_hoi",
                                         "ly_do_tu_choi", "hen_lai_sau")}
    v["ph_chu_dong"] = 1 if form.get("ph_chu_dong") else 0
    v["da_gui_thu_moi"] = 1 if form.get("da_gui_thu_moi") else 0
    tt, loi = v["tinh_trang"], []
    # lỗi ngày chỉ báo khi ô đó có nghĩa với tình trạng đã chọn (ô bị ẩn thì bị xoá bên dưới)
    loi_ngay: dict[str, list[str]] = {k: [] for k in ("ngay_hen_goi_lai", "ngay_hen_tham_quan", "ngay_nhap_hoc")}
    v["ngay_hen_goi_lai"] = _ngay_nhap(form, "ngay_hen_goi_lai", loi_ngay["ngay_hen_goi_lai"], "Ngày hẹn gọi lại")
    v["ngay_hen_tham_quan"] = _ngay_nhap(form, "ngay_hen_tham_quan", loi_ngay["ngay_hen_tham_quan"], "Ngày hẹn tham quan")
    v["ngay_nhap_hoc"] = _ngay_nhap(form, "ngay_nhap_hoc", loi_ngay["ngay_nhap_hoc"], "Ngày nhập học dự kiến")
    if v["phuong_thuc"] not in db.PHUONG_THUC:
        loi.append("Chọn phương thức liên hệ.")
    if tt not in q.TINH_TRANG:
        loi.append("Chọn tình trạng.")
    # Xoá giá trị ở ô không có nghĩa với tình trạng đã chọn (ô bị ẩn mà còn giá trị cũ).
    if tt in logic.KHONG_MUC_QUAN_TAM:
        v["muc_quan_tam"] = ""
    elif v["muc_quan_tam"] not in db.MUC_QUAN_TAM:
        loi.append("Chọn mức quan tâm.")
    if tt == q.TU_CHOI:
        if v["ly_do_tu_choi"] not in q.LY_DO_TU_CHOI:
            loi.append("Chọn lý do từ chối.")
    else:
        v["ly_do_tu_choi"] = ""
    if tt in logic.KHONG_HEN_LAI or v["hen_lai_sau"] not in logic.HEN_LAI_SAU:
        v["hen_lai_sau"] = ""
    if tt == q.GOI_LAI and not v["hen_lai_sau"]:
        loi.append("Phụ huynh hẹn gọi lại: chọn Hẹn lại sau.")
    if v["hen_lai_sau"] == q.HEN_CHON_NGAY:
        loi += loi_ngay["ngay_hen_goi_lai"]
        if not v["ngay_hen_goi_lai"] and not _chu_nhan(form, "ngay_hen_goi_lai"):
            loi.append("Chọn ngày hẹn gọi lại.")
    else:
        v["ngay_hen_goi_lai"] = None
    if tt == q.DA_HEN:
        loi += loi_ngay["ngay_hen_tham_quan"]
        if not v["ngay_hen_tham_quan"] and not _chu_nhan(form, "ngay_hen_tham_quan"):
            loi.append("Chọn ngày hẹn tham quan.")
    else:
        v["ngay_hen_tham_quan"] = None
    if tt != q.DAT_COC:
        v["da_gui_thu_moi"], v["ngay_nhap_hoc"] = 0, None
    else:
        loi += loi_ngay["ngay_nhap_hoc"]
    return v, loi


def _ve_form_cs(request, nguoi, r, v, loi, cs_id=None, status_code=200):
    return _ve(request, "ghi_nhan.html", nguoi, r=r, v=v, loi=loi, cs_id=cs_id, status_code=status_code,
               ds_phuong_thuc=db.PHUONG_THUC, ds_muc=db.MUC_QUAN_TAM, ds_hen=logic.HEN_LAI_SAU)


@app.get("/lead/{lead_id}/ghi-nhan", response_class=HTMLResponse)
def ghi_nhan_trang(request: Request, lead_id: int):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        r = logic.mot_lead(conn, nguoi, lead_id)
        if r is None:
            raise KhongThay()
        return _ve_form_cs(request, nguoi, r, {"phuong_thuc": "Gọi điện"}, [])
    finally:
        conn.close()


@app.post("/lead/{lead_id}/ghi-nhan")
async def ghi_nhan(request: Request, lead_id: int):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        r = logic.mot_lead(conn, nguoi, lead_id)
        if r is None:
            raise KhongThay()
        v, loi = _gia_tri_cham_soc(form)
        if loi:
            return _ve_form_cs(request, nguoi, r, v, loi, status_code=400)
        cot = list(v) + ["lead_id", "thoi_gian", "sale_id"]
        conn.execute(f"INSERT INTO cham_soc ({', '.join(cot)}) VALUES ({', '.join('?' * len(cot))})",
                     [*v.values(), lead_id, dongho.ghi_gio(dongho.bay_gio()), nguoi["id"]])
        conn.commit()
        return _ve_lai(f"/lead/{lead_id}")
    finally:
        conn.close()


def _mot_cham_soc(conn, nguoi, cs_id: int) -> tuple[sqlite3.Row, sqlite3.Row]:
    cs = conn.execute("SELECT * FROM cham_soc WHERE id = ?", (cs_id,)).fetchone()
    r = logic.mot_lead(conn, nguoi, cs["lead_id"]) if cs else None
    if cs is None or r is None:
        raise KhongThay()
    if nguoi["vai_tro"] != "chu" and cs["sale_id"] != nguoi["id"]:
        raise KhongDuQuyen()
    return cs, r


@app.get("/cham-soc/{cs_id}/sua", response_class=HTMLResponse)
def sua_cs_trang(request: Request, cs_id: int):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        cs, r = _mot_cham_soc(conn, nguoi, cs_id)
        return _ve_form_cs(request, nguoi, r, dict(cs), [], cs_id=cs_id)
    finally:
        conn.close()


@app.post("/cham-soc/{cs_id}/sua")
async def sua_cs(request: Request, cs_id: int):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        cs, r = _mot_cham_soc(conn, nguoi, cs_id)
        v, loi = _gia_tri_cham_soc(form)
        if loi:
            return _ve_form_cs(request, nguoi, r, v, loi, cs_id=cs_id, status_code=400)
        v["sua_luc"] = dongho.ghi_gio(dongho.bay_gio())
        conn.execute(f"UPDATE cham_soc SET {', '.join(k + ' = ?' for k in v)} WHERE id = ?", [*v.values(), cs_id])
        conn.commit()
        return _ve_lai(f"/lead/{r['id']}")
    finally:
        conn.close()


@app.post("/lead/{lead_id}/da-gui-thu-moi")
async def da_gui_thu_moi(request: Request, lead_id: int):
    await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        r = logic.mot_lead(conn, nguoi, lead_id)
        if r is None:
            raise KhongThay()
        cuoi = conn.execute("SELECT * FROM cham_soc WHERE lead_id = ? ORDER BY thoi_gian DESC, id DESC LIMIT 1",
                            (lead_id,)).fetchone()
        if cuoi is None or cuoi["tinh_trang"] != q.DAT_COC:
            raise KhongDuQuyen()
        conn.execute("UPDATE cham_soc SET da_gui_thu_moi = 1, sua_luc = ? WHERE id = ?",
                     (dongho.ghi_gio(dongho.bay_gio()), cuoi["id"]))
        conn.commit()
        return _ve_lai(f"/lead/{lead_id}")
    finally:
        conn.close()


# ------------------------------------------------------------------ tài khoản, Telegram

@app.get("/tai-khoan", response_class=HTMLResponse)
def tai_khoan(request: Request, ma: str = "", tb: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        # mã đang chờ lấy từ cơ sở dữ liệu, để link vẫn hiện sau khi bấm kiểm tra mà chưa thấy tin
        return _ve(request, "tai_khoan.html", nguoi, ma=nguoi["telegram_ma"] or "", tb=tb,
                   tg_cau_hinh=telegram.da_cau_hinh())
    finally:
        conn.close()


@app.post("/tai-khoan/mat-khau")
async def doi_mat_khau(request: Request):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        cu, moi, lai = form.get("cu") or "", form.get("moi") or "", form.get("lai") or ""
        if not auth.dung_mat_khau(cu, nguoi["mat_khau"]):
            tb = "Mật khẩu hiện tại chưa đúng."
        elif len(moi) < auth.MAT_KHAU_TOI_THIEU:
            tb = f"Mật khẩu mới cần ít nhất {auth.MAT_KHAU_TOI_THIEU} ký tự."
        elif moi != lai:
            tb = "Hai lần nhập mật khẩu mới không giống nhau."
        else:
            conn.execute("UPDATE nguoi_dung SET mat_khau = ?, phien = phien + 1 WHERE id = ?",
                         (auth.bam(moi), nguoi["id"]))
            conn.commit()
            request.session.update(phien=nguoi["phien"] + 1)
            tb = "Đã đổi mật khẩu. Các máy khác đang đăng nhập tài khoản này sẽ phải đăng nhập lại."
        return _ve_lai("/tai-khoan?" + urlencode({"tb": tb}))
    finally:
        conn.close()


@app.post("/tai-khoan/telegram")
async def noi_telegram(request: Request):
    await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        telegram.tao_ma_noi(conn, nguoi["id"])
        return _ve_lai("/tai-khoan")
    finally:
        conn.close()


def _doc_telegram() -> None:
    conn = _conn()
    try:
        telegram.xu_ly_cap_nhat(conn)
    finally:
        conn.close()


@app.post("/tai-khoan/telegram/kiem-tra")
async def kiem_tra_telegram(request: Request):
    await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        await run_in_threadpool(_doc_telegram)
        r = conn.execute("SELECT telegram_chat_id FROM nguoi_dung WHERE id = ?", (nguoi["id"],)).fetchone()
        tb = ("Đã nối Telegram." if r["telegram_chat_id"] else
              "Chưa thấy tin của bạn. Mở đường link, bấm Bắt đầu (Start) trong Telegram, chờ bot trả lời rồi bấm "
              "kiểm tra lại. Tin có biểu tượng đồng hồ nghĩa là Telegram chưa gửi được: thử bật VPN hoặc đổi mạng.")
        return _ve_lai("/tai-khoan?" + urlencode({"tb": tb}))
    finally:
        conn.close()


# ------------------------------------------------------------------ chủ: người dùng

@app.get("/quan-tri/nguoi-dung", response_class=HTMLResponse)
def nguoi_dung(request: Request, tb: str = ""):
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ds = list(conn.execute("SELECT * FROM nguoi_dung ORDER BY dang_lam DESC, vai_tro, ten"))
        return _ve(request, "nguoi_dung.html", nguoi, ds=ds, tb=tb, ds_co_so=db.danh_muc(conn, "Cơ sở"))
    finally:
        conn.close()


@app.post("/quan-tri/nguoi-dung")
async def them_nguoi_dung(request: Request):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        ten_dn = _chu_nhan(form, "ten_dang_nhap").lower()
        ten, mk = _chu_nhan(form, "ten"), form.get("mat_khau") or ""
        vai = "chu" if form.get("vai_tro") == "chu" else "sale"
        if not ten_dn.isascii() or not ten_dn.replace(".", "").replace("_", "").isalnum() or not ten:
            tb = "Tên đăng nhập chỉ gồm chữ không dấu và số; tên hiển thị không để trống."
        elif len(mk) < auth.MAT_KHAU_TOI_THIEU:
            tb = f"Mật khẩu cần ít nhất {auth.MAT_KHAU_TOI_THIEU} ký tự."
        elif conn.execute("SELECT 1 FROM nguoi_dung WHERE ten_dang_nhap = ?", (ten_dn,)).fetchone():
            tb = "Tên đăng nhập này đã có."
        else:
            conn.execute("INSERT INTO nguoi_dung (ten_dang_nhap, ten, co_so, vai_tro, mat_khau, tao_luc) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (ten_dn, ten, _chu_nhan(form, "co_so"), vai, auth.bam(mk), dongho.ghi_gio(dongho.bay_gio())))
            conn.commit()
            tb = f"Đã tạo tài khoản {ten_dn}. Gửi mật khẩu cho người đó và nhắc họ đổi lại."
        return _ve_lai("/quan-tri/nguoi-dung?" + urlencode({"tb": tb}))
    finally:
        conn.close()


@app.post("/quan-tri/nguoi-dung/{uid}")
async def sua_nguoi_dung(request: Request, uid: int):
    form = await _bieu_mau(request)
    conn = _conn()
    try:
        nguoi = _nguoi(request, conn)
        _chu(nguoi)
        viec = form.get("viec")
        if viec == "dat_mat_khau":
            mk = form.get("mat_khau") or ""
            if len(mk) < auth.MAT_KHAU_TOI_THIEU:
                tb = f"Mật khẩu cần ít nhất {auth.MAT_KHAU_TOI_THIEU} ký tự."
            else:
                conn.execute("UPDATE nguoi_dung SET mat_khau = ?, phien = phien + 1 WHERE id = ?", (auth.bam(mk), uid))
                tb = "Đã đặt lại mật khẩu."
        elif viec == "nghi" and uid != nguoi["id"]:
            # gỡ nối Telegram: người đã nghỉ không được nhận tin có tên phụ huynh nữa (bật lại thì nối lại)
            conn.execute("UPDATE nguoi_dung SET dang_lam = 0, phien = phien + 1, telegram_chat_id = NULL, "
                         "telegram_ma = NULL WHERE id = ?", (uid,))
            tb = "Đã tắt tài khoản và gỡ nối Telegram. Lead của người này vẫn giữ nguyên: nhớ chuyển cho sale khác."
        elif viec == "lam_lai":
            conn.execute("UPDATE nguoi_dung SET dang_lam = 1 WHERE id = ?", (uid,))
            tb = "Đã bật lại tài khoản."
        else:
            tb = "Không làm gì."
        conn.commit()
        return _ve_lai("/quan-tri/nguoi-dung?" + urlencode({"tb": tb}))
    finally:
        conn.close()


# Màn của chủ (đợt B) nằm ở app/chu.py; nạp sau cùng vì nó dùng các tiện ích ở trên.
from . import chu  # noqa: E402

app.include_router(chu.router)
