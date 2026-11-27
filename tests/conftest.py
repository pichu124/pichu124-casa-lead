import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))
# Test luôn chạy cách ly, kể cả khi shell đang mang cấu hình máy thật (vd sau `. /etc/casa-lead.env`):
# không dùng thư mục dữ liệu thật, không bật chế độ production (cookie chỉ qua HTTPS), không cầm token Telegram thật,
# không gọi Sheet thật của bot (dữ liệu phụ huynh thật không được vào test).
for _bien in ("CASA_LEAD_ENV", "CASA_LEAD_SECRET", "CASA_LEAD_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME",
              "LEADS_SHEET_WEBHOOK_URL", "LEADS_READ_TOKEN"):
    os.environ.pop(_bien, None)
os.environ["CASA_LEAD_DATA"] = tempfile.mkdtemp(prefix="casa-lead-test-")
# Không bao giờ đọc tệp đăng ký thật của website (mặc định /var/lib/casa-website/dang-ky.jsonl trên VPS)
os.environ["CASA_WEBSITE_DANG_KY"] = os.path.join(os.environ["CASA_LEAD_DATA"], "khong-co-dang-ky.jsonl")

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, db, dongho, telegram  # noqa: E402
from app.main import app  # noqa: E402
from scripts import du_lieu_mau  # noqa: E402

MK = du_lieu_mau.MAT_KHAU_MAU


@pytest.fixture
def du_lieu(tmp_path, monkeypatch):
    """Cơ sở dữ liệu mới có dữ liệu mẫu (ngày gốc 02/11/2026), đồng hồ đặt 10:00 ngày 04/11/2026."""
    monkeypatch.setenv("CASA_LEAD_DATA", str(tmp_path))
    auth._lan_sai.clear()
    conn = db.ket_noi()
    db.khoi_tao(conn)
    du_lieu_mau.nap(conn, date(2026, 11, 2))
    conn.close()
    monkeypatch.setattr(dongho, "GIO_CO_DINH", datetime(2026, 11, 4, 10, 0))
    da_gui = []
    monkeypatch.setattr(telegram, "gui_tin", lambda chat, tin: da_gui.append((chat, tin)) or True)
    return da_gui


def csrf(client, url="/dang-nhap"):
    r = client.get(url)
    m = re.search(r'name="csrf" value="([^"]+)"', r.text)
    assert m, f"không thấy mã biểu mẫu ở {url}"
    return m.group(1)


def dang_nhap(ten, mk=MK):
    c = TestClient(app)
    r = c.post("/dang-nhap", data={"csrf": csrf(c), "ten_dang_nhap": ten, "mat_khau": mk}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return c


def id_lead(ten_ph):
    conn = db.ket_noi()
    try:
        return conn.execute("SELECT id FROM lead WHERE ten_ph = ?", (ten_ph,)).fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def sale(du_lieu):
    return dang_nhap
