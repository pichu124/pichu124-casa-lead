"""Đọc tệp đăng ký của website định kỳ và báo ngay vào Telegram khi có phụ huynh mới chờ giao sale.

Chạy kèm cron 5 phút của Messenger (`python -m app.dong_bo_messenger` gọi `chay` ở đây), nên không cần thêm dòng
cron. Chạy riêng được: `python -m app.dong_bo_website`.

Báo vào nhóm Telegram đã nối; chưa nối nhóm thì báo riêng cho chủ. Mỗi đăng ký báo một lần (he_thong
`website_da_bao`); lần chạy đầu chỉ ghi nhớ những đăng ký đang chờ, không báo dồn. Tin không chứa SĐT.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys

from . import db, telegram, website

log = logging.getLogger("casa_lead.dong_bo_website")
DA_BAO = "website_da_bao"


def _tin(moi: list[dict]) -> str:
    dong = [f"🌐 Website mới: {len(moi)} phụ huynh đăng ký tham quan, chờ giao sale."]
    for h in moi:
        be = f" (bé sinh {h['sinh']})" if h.get("sinh") else ""
        them = " · ".join(x for x in (h.get("ten_co_so"), h.get("gio_vn")) if x)
        dong.append(f"- {h.get('ten') or 'Phụ huynh'}{be}" + (f" · {them}" if them else ""))
    dong.append("Mở app → Quản trị → Website chưa nhận để giao lead.")
    return "\n".join(dong)


def chay(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Đọc tệp rồi báo đăng ký mới chờ giao. Trả các tin đã gửi (người nhận, nội dung). Không ném lỗi."""
    if website.dong_bo(conn) is None:
        return []
    cho = website.chua_nhan(conn, kem_trung=False)
    luu = db.lay_he_thong(conn, DA_BAO)
    if not luu:  # lần đầu: ghi nhớ, không báo những đăng ký đã có từ trước
        db.dat_he_thong(conn, DA_BAO, json.dumps(sorted(h["ma"] for h in cho)))
        conn.commit()
        return []
    da_bao = set(json.loads(luu))
    moi = [h for h in cho if h["ma"] not in da_bao]
    if not moi:
        return []
    tin = _tin(moi)
    gui = []
    for chat in telegram.nguoi_nhan_quan_ly(conn):
        if telegram.gui_tin(chat, tin):
            gui.append((chat, tin))
        else:
            log.warning("Không báo được đăng ký website mới vào Telegram (lỗi mạng hoặc bot bị gỡ)")
    if gui or not telegram.nguoi_nhan_quan_ly(conn):  # gửi lỗi hết thì để lần sau báo lại
        db.dat_he_thong(conn, DA_BAO, json.dumps(sorted(da_bao | {h["ma"] for h in moi})))
        conn.commit()
    return gui


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = db.ket_noi()
    try:
        db.khoi_tao(conn)
        gui = chay(conn)
        if gui:
            log.info("Đã báo đăng ký website mới tới %d nơi", len(gui))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
