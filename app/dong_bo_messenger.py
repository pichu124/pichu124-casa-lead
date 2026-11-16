"""Lấy tab Leads của bot Messenger định kỳ (cron mỗi 5 phút) và báo ngay vào Telegram khi có phụ huynh mới chờ
giao sale, để chủ giao lead và sale gọi trong ngày thay vì đợi tới tin nhắc sáng.

    python -m app.dong_bo_messenger

Báo vào nhóm Telegram đã nối; chưa nối nhóm thì báo riêng cho chủ. Mỗi phụ huynh báo một lần (he_thong
`messenger_da_bao`); lần chạy đầu chỉ ghi nhớ những người đang chờ, không báo dồn. Tin không chứa SĐT.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys

from . import db, messenger, telegram

log = logging.getLogger("casa_lead.dong_bo_messenger")
DA_BAO = "messenger_da_bao"


def _nguoi_nhan(conn: sqlite3.Connection) -> list[str]:
    nhom = db.lay_he_thong(conn, "telegram_nhom")
    if nhom:
        return [nhom]
    return [r[0] for r in conn.execute("SELECT telegram_chat_id FROM nguoi_dung WHERE vai_tro = 'chu' "
                                       "AND dang_lam = 1 AND telegram_chat_id != ''")]


def _tin(moi: list[dict]) -> str:
    dong = [f"📩 Messenger mới: {len(moi)} phụ huynh để SĐT cho bot, chờ giao sale."]
    for h in moi:
        be = f" (bé {h['kid_name']})" if h.get("kid_name") else ""
        them = " · ".join(x for x in (h.get("campus"), h.get("cap_nhat_vn")) if x)
        dong.append(f"- {h.get('fb_name') or 'Phụ huynh'}{be}" + (f" · {them}" if them else ""))
    dong.append("Mở app → Quản trị → Messenger chưa nhận để giao lead.")
    return "\n".join(dong)


def chay(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Lấy Sheet rồi báo phụ huynh mới chờ giao. Trả các tin đã gửi (người nhận, nội dung). Không ném lỗi."""
    if messenger.dong_bo(conn) is None:  # chưa cấu hình hoặc Sheet lỗi: giữ nguyên, lần sau thử lại
        return []
    cho = messenger.chua_nhan(conn, kem_trung=False)
    luu = db.lay_he_thong(conn, DA_BAO)
    if not luu:  # lần đầu: ghi nhớ, không báo những người đã chờ từ trước
        db.dat_he_thong(conn, DA_BAO, json.dumps(sorted(h["customer_id"] for h in cho)))
        conn.commit()
        return []
    da_bao = set(json.loads(luu))
    moi = [h for h in cho if h["customer_id"] not in da_bao]
    if not moi:
        return []
    tin = _tin(moi)
    gui = []
    for chat in _nguoi_nhan(conn):
        if telegram.gui_tin(chat, tin):
            gui.append((chat, tin))
        else:
            log.warning("Không báo được Messenger mới vào Telegram (lỗi mạng hoặc bot bị gỡ)")
    if gui or not _nguoi_nhan(conn):  # gửi lỗi hết thì để lần sau báo lại
        db.dat_he_thong(conn, DA_BAO, json.dumps(sorted(da_bao | {h["customer_id"] for h in moi})))
        conn.commit()
    return gui


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx ghi mỗi request kèm URL web app ở mức INFO: không để cron 5 phút một lần chép nó vào log
    logging.getLogger("httpx").setLevel(logging.WARNING)
    conn = db.ket_noi()
    try:
        db.khoi_tao(conn)
        gui = chay(conn)
        if gui:
            log.info("Đã báo Messenger mới tới %d nơi", len(gui))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
