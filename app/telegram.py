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
# Chuỗi chữ số có thể kèm dấu cách, chấm, gạch, ngoặc: đủ 9 chữ số trở lên thì coi là SĐT.
# Không gồm "/" nên ngày dạng 04/11/2026 không bị che.
CUM_SO = re.compile(r"\+?\(?\d[\d .()\-]{6,}\d\)?")
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
    ma = secrets.token_hex(8)
    conn.execute("UPDATE nguoi_dung SET telegram_ma = ? WHERE id = ?", (ma, nguoi_id))
    conn.commit()
    return ma


def xu_ly_cap_nhat(conn: sqlite3.Connection, cap_nhat: list[dict] | None = None) -> int:
    """Đọc các tin "/start <mã>" người dùng gửi bot, ghi chat_id cho đúng tài khoản. Trả về số tài khoản vừa nối."""
    ds = _lay_cap_nhat(conn) if cap_nhat is None else cap_nhat
    so = 0
    for u in ds:
        m = u.get("message") or {}
        chu = (m.get("text") or "").strip()
        if not chu.startswith("/start "):
            continue
        ma = chu.split(maxsplit=1)[1].strip()
        chat = str((m.get("chat") or {}).get("id", ""))
        if not ma or not chat:
            continue
        cur = conn.execute("UPDATE nguoi_dung SET telegram_chat_id = ?, telegram_ma = NULL WHERE telegram_ma = ?",
                           (chat, ma))
        if cur.rowcount:
            so += 1
            gui_tin(chat, "Đã nối Telegram với app Casa chăm sóc lead. Mỗi sáng ngày làm việc bạn sẽ nhận danh sách cần liên hệ ở đây.")
    conn.commit()
    return so
