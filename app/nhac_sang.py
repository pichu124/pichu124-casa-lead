"""Tin nhắc buổi sáng qua Telegram, chạy bằng lịch của máy chủ (cron) lúc 8:00.

    python -m app.nhac_sang            # gửi (bỏ qua thứ 7, Chủ nhật, ngày nghỉ)
    python -m app.nhac_sang --thu      # chỉ in ra màn hình, không gửi
    python -m app.nhac_sang --ngay 2026-11-16 --thu

Mỗi sale nhận danh sách phụ huynh cần liên hệ hôm nay và quá hạn, kèm việc cần làm.
Chủ nhận lead mới chưa ai liên hệ đã quá hạn và số lead bỏ quên. Tin không chứa SĐT.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import date

from . import db, dongho, logic, messenger, quy_tac_nhac as q, telegram

log = logging.getLogger("casa_lead.nhac_sang")


def _dong(lt: logic.LeadTinh) -> str:
    be = f" (bé {lt.row['ten_be']})" if lt.row["ten_be"] else ""
    khan = f"quá hạn {lt.so_ngay_qua_han} ngày" if lt.so_ngay_qua_han else lt.khan.lower()
    return f"- {lt.row['ten_ph']}{be}, {khan}: {lt.viec or 'Liên hệ'}"


def _dong_gui(v: logic.ViecGui) -> str:
    be = f" (bé {v.lt.row['ten_be']})" if v.lt.row["ten_be"] else ""
    khan = f"quá hạn {v.so_ngay_qua_han} ngày" if v.so_ngay_qua_han else "hôm nay"
    return f"- {v.lt.row['ten_ph']}{be}, {khan}: {logic.TEN_VIEC_GUI[v.loai]}"


def _viec_cua(conn: sqlite3.Connection, nguoi: sqlite3.Row, hom_nay: date) -> tuple[list, list]:
    """(lead cần liên hệ hôm nay hoặc quá hạn, việc gửi ưu đãi / thông tin đã đến hạn) của một sale."""
    tat = logic.tinh(conn, logic.lead_cua(conn, nguoi), hom_nay)
    ds = sorted((lt for lt in tat if lt.khan in ("Quá hạn", "Hôm nay")), key=lambda lt: (lt.han, lt.row["id"]))
    return ds, logic.viec_gui(conn, tat, hom_nay)


def tin_cho_sale(conn: sqlite3.Connection, sale: sqlite3.Row, hom_nay: date) -> str | None:
    ds, gui = _viec_cua(conn, sale, hom_nay)
    if not ds and not gui:
        return None
    qua_han = sum(lt.khan == "Quá hạn" for lt in ds)
    dong = [f"Chào {sale['ten']},", "",
            f"Hôm nay bạn có {len(ds) - qua_han} phụ huynh cần liên hệ và {qua_han} phụ huynh đã quá hạn"
            + (f", cộng {len(gui)} việc gửi ưu đãi / thông tin." if gui else "."), ""]
    dong += [_dong(lt) for lt in ds] + [_dong_gui(v) for v in gui]
    url = os.environ.get("CASA_LEAD_URL", "")
    dong += ["", "Gọi xong nhớ ghi nhận trong app" + (f": {url}" if url else ".")]
    return "\n".join(dong)


def tin_cho_chu(conn: sqlite3.Connection, chu: sqlite3.Row, hom_nay: date) -> str:
    tat_ca = logic.tinh(conn, logic.lead_cua(conn, chu), hom_nay)
    moi = [lt for lt in tat_ca if lt.lan_cuoi is None and not lt.row["tam_dung"] and lt.khan == "Quá hạn"]
    bo_quen = [lt for lt in tat_ca if q.bo_quen(lt.giai_doan, lt.khan)]
    dong = [f"Chào {chu['ten']},", "", f"Lead mới chưa ai liên hệ (đã quá hạn): {len(moi)}"]
    dong += [f"- {lt.row['ten_ph']} · sale {lt.row['ten_sale'] or 'chưa giao'} · nhận {dongho.doc_gio(lt.row['ngay_nhan']):%d/%m}"
             for lt in moi]
    dong += ["", f"Lead bỏ quên (đang chăm sóc mà quá hạn): {len(bo_quen)}"]
    if logic.so_chua_giao(conn):
        dong += [f"⚠ Lead chưa giao sale: {logic.so_chua_giao(conn)} (mở app → Tất cả lead)"]
    if messenger.da_cau_hinh():
        dong += [f"Messenger chưa giao: {messenger.so_chua_nhan(conn)} (Quản trị → Messenger chưa nhận)"]
    return "\n".join(dong)


def tin_cho_nhom(conn: sqlite3.Connection, hom_nay: date) -> str:
    """Một tin cho nhóm quản lý: việc của từng sale, rồi phần của chủ. Không chứa SĐT."""
    dong = [f"📋 Nhắc việc sáng {hom_nay:%d/%m/%Y}"]
    chu = None
    for nguoi in conn.execute("SELECT * FROM nguoi_dung WHERE dang_lam = 1 ORDER BY ten"):
        if nguoi["vai_tro"] == "chu":
            chu = chu or nguoi
            continue
        ds, gui = _viec_cua(conn, nguoi, hom_nay)
        if not ds and not gui:
            continue
        qua_han = sum(lt.khan == "Quá hạn" for lt in ds)
        co_so = f" ({nguoi['co_so']})" if nguoi["co_so"] else ""
        dong += ["", f"— {nguoi['ten']}{co_so}: {len(ds) - qua_han} hôm nay, {qua_han} quá hạn"
                 + (f", {len(gui)} việc gửi" if gui else "")]
        dong += [_dong(lt) for lt in ds] + [_dong_gui(v) for v in gui]
    if len(dong) == 1:
        dong += ["", "Hôm nay không sale nào có phụ huynh đến hạn liên hệ."]
    if chu is not None:
        tat_ca = logic.tinh(conn, logic.lead_cua(conn, chu), hom_nay)
        moi = [lt for lt in tat_ca if lt.lan_cuoi is None and not lt.row["tam_dung"] and lt.khan == "Quá hạn"]
        bo_quen = [lt for lt in tat_ca if q.bo_quen(lt.giai_doan, lt.khan)]
        dong += ["", f"Lead mới chưa ai liên hệ (đã quá hạn): {len(moi)}"]
        dong += [f"- {lt.row['ten_ph']} · sale {lt.row['ten_sale'] or 'chưa giao'} · nhận "
                 f"{dongho.doc_gio(lt.row['ngay_nhan']):%d/%m}" for lt in moi]
        dong += [f"Bỏ quên (đang chăm sóc mà quá hạn): {len(bo_quen)}"]
        if logic.so_chua_giao(conn):
            dong += [f"⚠ Lead chưa giao sale: {logic.so_chua_giao(conn)} (mở app → Tất cả lead)"]
        if messenger.da_cau_hinh():
            dong += [f"Messenger chưa giao: {messenger.so_chua_nhan(conn)}"]
    url = os.environ.get("CASA_LEAD_URL", "")
    if url:
        dong += ["", url]
    return "\n".join(dong)


def chay(conn: sqlite3.Connection, hom_nay: date, thu: bool = False, gui=None) -> list[tuple[str, str]]:
    """Trả về danh sách (người nhận, nội dung) đã gửi hoặc sẽ gửi. Đã nối nhóm Telegram thì chỉ gửi một tin vào
    nhóm (thay cho tin riêng buổi sáng); chưa nối thì mỗi người nhận tin riêng."""
    gui = gui or telegram.gui_tin
    if q.la_ngay_nghi(hom_nay, logic.ngay_nghi(conn)):
        return []
    if not thu:
        try:  # để số "Messenger chưa giao" là số mới nhất; lỗi gì cũng không được chặn tin nhắc sáng
            messenger.dong_bo(conn)
        except Exception:  # noqa: BLE001
            log.exception("Đồng bộ lead Messenger lỗi; tin nhắc dùng dữ liệu cũ")
    nhom = db.lay_he_thong(conn, "telegram_nhom")
    if nhom:
        tin = tin_cho_nhom(conn, hom_nay)
        if not thu and not gui(nhom, tin):
            log.warning("Không gửi được tin nhắc sáng vào nhóm Telegram (bot bị gỡ khỏi nhóm hoặc lỗi mạng)")
        return [(f"nhóm {db.lay_he_thong(conn, 'telegram_nhom_ten') or nhom}", tin)]
    kq = []
    for nguoi in conn.execute("SELECT * FROM nguoi_dung WHERE dang_lam = 1 ORDER BY id"):
        tin = tin_cho_chu(conn, nguoi, hom_nay) if nguoi["vai_tro"] == "chu" else tin_cho_sale(conn, nguoi, hom_nay)
        if not tin:
            continue
        kq.append((nguoi["ten_dang_nhap"], tin))
        if not thu and not gui(nguoi["telegram_chat_id"] or "", tin):
            log.warning("Không gửi được tin nhắc sáng cho %s (chưa nối Telegram hoặc lỗi mạng)", nguoi["ten_dang_nhap"])
    return kq


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gửi tin nhắc buổi sáng qua Telegram")
    p.add_argument("--thu", action="store_true", help="chỉ in ra, không gửi")
    p.add_argument("--ngay", help="ngày tính (YYYY-MM-DD), mặc định hôm nay")
    a = p.parse_args(argv)
    hom_nay = date.fromisoformat(a.ngay) if a.ngay else dongho.hom_nay()
    conn = db.ket_noi()
    db.khoi_tao(conn)
    ds = chay(conn, hom_nay, thu=a.thu)
    if not ds:
        print(f"{hom_nay:%d/%m/%Y}: ngày nghỉ hoặc không có ai cần nhắc.")
    for ai, tin in ds:
        print(f"--- {ai}\n{tin}\n" if a.thu else f"Đã xử lý: {ai}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
