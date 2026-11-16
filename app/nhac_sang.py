"""Tin nhắc buổi sáng qua Telegram, chạy bằng lịch của máy chủ (cron) lúc 8:00.

    python -m app.nhac_sang            # gửi (bỏ qua thứ 7, Chủ nhật, ngày nghỉ)
    python -m app.nhac_sang --thu      # chỉ in ra màn hình, không gửi
    python -m app.nhac_sang --ngay 2026-11-16 --thu

Mỗi sale nhận danh sách phụ huynh cần liên hệ hôm nay và quá hạn, kèm việc cần làm.
Chủ nhận lead mới chưa ai liên hệ đã quá hạn và số lead bỏ quên. Tin không chứa SĐT.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date

from . import db, dongho, logic, quy_tac_nhac as q, telegram


def _dong(lt: logic.LeadTinh) -> str:
    be = f" (bé {lt.row['ten_be']})" if lt.row["ten_be"] else ""
    return f"- {lt.row['ten_ph']}{be}, {lt.khan}: {lt.viec or 'Liên hệ'}"


def tin_cho_sale(conn: sqlite3.Connection, sale: sqlite3.Row, hom_nay: date) -> str | None:
    ds = [lt for lt in logic.tinh(conn, logic.lead_cua(conn, sale), hom_nay) if lt.khan in ("Quá hạn", "Hôm nay")]
    if not ds:
        return None
    ds.sort(key=lambda lt: (lt.han, lt.row["id"]))
    qua_han = sum(lt.khan == "Quá hạn" for lt in ds)
    dong = [f"Chào {sale['ten']},", "",
            f"Hôm nay bạn có {len(ds) - qua_han} phụ huynh cần liên hệ và {qua_han} phụ huynh đã quá hạn.", ""]
    dong += [_dong(lt) for lt in ds]
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
    return "\n".join(dong)


def chay(conn: sqlite3.Connection, hom_nay: date, thu: bool = False, gui=None) -> list[tuple[str, str]]:
    """Trả về danh sách (người nhận, nội dung) đã gửi hoặc sẽ gửi."""
    gui = gui or telegram.gui_tin
    if q.la_ngay_nghi(hom_nay, logic.ngay_nghi(conn)):
        return []
    kq = []
    for nguoi in conn.execute("SELECT * FROM nguoi_dung WHERE dang_lam = 1 ORDER BY id"):
        tin = tin_cho_chu(conn, nguoi, hom_nay) if nguoi["vai_tro"] == "chu" else tin_cho_sale(conn, nguoi, hom_nay)
        if not tin:
            continue
        kq.append((nguoi["ten_dang_nhap"], tin))
        if not thu:
            gui(nguoi["telegram_chat_id"] or "", tin)
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
        print(f"--- {ai}\n{tin}\n" if a.thu else f"Đã gửi: {ai}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
