"""Gửi tin nhắc qua Telegram và nối tài khoản Telegram của từng người.

Dùng một bot Telegram RIÊNG cho app này (tạo bằng @BotFather), không dùng chung bot Messenger:
app đọc tin của bot bằng getUpdates, cách này không chạy được khi bot đã đặt webhook.
Biến môi trường: TELEGRAM_BOT_TOKEN (bí mật, không ghi vào kho mã), TELEGRAM_BOT_USERNAME.
Tin gửi đi KHÔNG BAO GIỜ chứa số điện thoại phụ huynh.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import sqlite3

import httpx

from .db import dat_he_thong, lay_he_thong

log = logging.getLogger("casa_lead.telegram")
# Chuỗi chữ số có thể kèm dấu ngăn (cách thường, cách cứng, chấm, phẩy, gạch nối, gạch dài, dấu trừ, gạch dưới, ngoặc):
# đủ 9 chữ số trở lên thì coi là SĐT. Không gồm "/" (giữ ngày 04/11/2026) và không gồm xuống dòng.
CUM_SO = re.compile(r"\+?\(?\d(?:[\d.,()_\-\u2010-\u2015\u2212]|[^\S\n]){6,}\d\)?")
DAI_TIN = 3500  # Telegram từ chối tin dài hơn 4096 ký tự


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def ten_bot() -> str:
    return os.environ.get("TELEGRAM_BOT_USERNAME", "")


def da_cau_hinh() -> bool:
    return bool(_token())


def an_sdt(s: str) -> str:
    """Lớp chặn cuối: dù ai đó gõ SĐT vào tên hay ghi chú, tin Telegram cũng không mang SĐT đi."""
    return CUM_SO.sub(lambda m: "[SĐT]" if sum(ch.isdigit() for ch in m.group()) >= 9 else m.group(), s)


def chia_tin(s: str, toi_da: int = DAI_TIN) -> list[str]:
    """Chia tin dài theo dòng thành nhiều tin, mỗi tin không quá `toi_da` ký tự."""
    phan, hien = [], ""
    for dong in s.split("\n"):
        while len(dong) > toi_da:
            if hien:
                phan.append(hien)
                hien = ""
            phan.append(dong[:toi_da])
            dong = dong[toi_da:]
        if hien and len(hien) + 1 + len(dong) > toi_da:
            phan.append(hien)
            hien = dong
        else:
            hien = f"{hien}\n{dong}" if hien else dong
    if hien:
        phan.append(hien)
    return phan


def nguoi_nhan_quan_ly(conn: sqlite3.Connection) -> list[str]:
    """Nơi nhận tin cho quản lý: nhóm Telegram đã nối, chưa nối thì từng chủ đang làm đã nối Telegram."""
    nhom = lay_he_thong(conn, "telegram_nhom")
    if nhom:
        return [nhom]
    return [r[0] for r in conn.execute("SELECT telegram_chat_id FROM nguoi_dung WHERE vai_tro = 'chu' "
                                       "AND dang_lam = 1 AND telegram_chat_id != ''")]


def gui_tin(chat_id: str, noi_dung: str) -> bool:
    """Gửi một tin. Trả về False (và ghi log, không kèm nội dung) khi chưa cấu hình hoặc lỗi."""
    if not _token() or not chat_id:
        log.warning("Chưa cấu hình Telegram hoặc người nhận chưa nối Telegram: bỏ qua một tin")
        return False
    for phan in chia_tin(an_sdt(noi_dung)):
        try:
            r = httpx.post(f"https://api.telegram.org/bot{_token()}/sendMessage",
                           json={"chat_id": chat_id, "text": phan, "disable_web_page_preview": True}, timeout=15)
        except httpx.HTTPError as e:
            log.warning("Không gửi được tin Telegram: %s", type(e).__name__)
            return False
        if r.status_code != 200:
            log.warning("Telegram trả lỗi %s khi gửi tin", r.status_code)
            return False
    return True


def _lay_cap_nhat(conn: sqlite3.Connection) -> list[dict]:
    if not _token():
        return []
    offset = int(lay_he_thong(conn, "telegram_offset", "0") or 0)
    try:
        r = httpx.get(f"https://api.telegram.org/bot{_token()}/getUpdates",
                      params={"offset": offset, "timeout": 0, "allowed_updates": '["message"]'}, timeout=15)
        ds = r.json().get("result", []) if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Không đọc được tin Telegram: %s", type(e).__name__)
        return []
    if ds:
        dat_he_thong(conn, "telegram_offset", str(ds[-1]["update_id"] + 1))
        conn.commit()
    return ds


def tao_ma_noi(conn: sqlite3.Connection, nguoi_id: int) -> str:
    """Mã nối Telegram của người này. Đã có mã chưa dùng thì giữ nguyên (bấm Nối lần nữa không làm hỏng
    tin /start đang trên đường tới)."""
    r = conn.execute("SELECT telegram_ma FROM nguoi_dung WHERE id = ?", (nguoi_id,)).fetchone()
    if r and r[0]:
        return r[0]
    ma = secrets.token_hex(8)
    conn.execute("UPDATE nguoi_dung SET telegram_ma = ? WHERE id = ?", (ma, nguoi_id))
    conn.commit()
    return ma


def tao_ma_nhom(conn: sqlite3.Connection) -> str:
    """Mã để nối nhóm Telegram nhận tin nhắc sáng. Đã có mã chưa dùng thì giữ nguyên."""
    ma = lay_he_thong(conn, "telegram_nhom_ma")
    if not ma:
        ma = secrets.token_hex(8)
        dat_he_thong(conn, "telegram_nhom_ma", ma)
        conn.commit()
    return ma


def _xu_ly_nhom(conn: sqlite3.Connection, m: dict, chat: str, chu: str) -> bool:
    """Tin trong nhóm: chỉ quan tâm lệnh /noi <mã> (hoặc /start <mã>) và việc nhóm đổi mã khi lên supergroup.
    Mọi tin khác trong nhóm: im lặng. Trả về True khi vừa nối nhóm."""
    moi = m.get("migrate_to_chat_id")
    if moi and chat == lay_he_thong(conn, "telegram_nhom"):
        dat_he_thong(conn, "telegram_nhom", str(moi))
        return False
    lenh = re.fullmatch(r"/(?:noi|start)(?:@\w+)?\s+([0-9a-f]{16})", chu)
    ma = lay_he_thong(conn, "telegram_nhom_ma")
    if not lenh or not ma or lenh.group(1) != ma:
        return False
    dat_he_thong(conn, "telegram_nhom", chat)
    dat_he_thong(conn, "telegram_nhom_ten", (m.get("chat") or {}).get("title") or "")
    dat_he_thong(conn, "telegram_nhom_ma", "")
    gui_tin(chat, "Đã nối nhóm này với app Casa chăm sóc lead. Mỗi sáng ngày làm việc lúc 8:00 nhóm nhận danh "
                  "sách phụ huynh cần liên hệ của từng sale.")
    return True


HUONG_DAN = ("Chào bạn. Để nhận tin nhắc, mở app Casa chăm sóc lead → Tài khoản → Nối Telegram, "
             "rồi bấm đường link trên màn hình (hoặc gửi cho bot mã 16 ký tự hiện trên màn hình).")


def xu_ly_cap_nhat(conn: sqlite3.Connection, cap_nhat: list[dict] | None = None) -> int:
    """Đọc các tin "/start <mã>" người dùng gửi bot, ghi chat_id cho đúng tài khoản. Trả về số tài khoản vừa nối."""
    ds = _lay_cap_nhat(conn) if cap_nhat is None else cap_nhat
    so = 0
    for u in ds:
        m = u.get("message") or {}
        chat_obj = m.get("chat") or {}
        chat = str(chat_obj.get("id", ""))
        chu = (m.get("text") or "").strip()
        if chat and chat_obj.get("type", "private") != "private":
            _xu_ly_nhom(conn, m, chat, chu)
            continue
        if not chat or not chu:
            continue
        # "/start <mã>" từ đường link, hoặc người dùng tự gửi mã
        ma = chu.split(maxsplit=1)[1].strip() if chu.startswith("/start ") else chu
        cur = conn.execute("UPDATE nguoi_dung SET telegram_chat_id = ?, telegram_ma = NULL WHERE telegram_ma = ?",
                           (chat, ma)) if re.fullmatch(r"[0-9a-f]{16}", ma) else None
        if cur is not None and cur.rowcount:
            so += 1
            gui_tin(chat, "Đã nối Telegram với app Casa chăm sóc lead. Mỗi sáng ngày làm việc bạn sẽ nhận danh sách cần liên hệ ở đây.")
        else:
            gui_tin(chat, HUONG_DAN)
    conn.commit()
    return so
