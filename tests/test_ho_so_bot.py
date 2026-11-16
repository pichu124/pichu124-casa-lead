"""Hồ sơ lead đến từ Messenger có khung "Chatbot đã tư vấn / đã gửi" lấy từ Sheet đã đồng bộ (tự cập nhật, cả lead
giao trước khi có tính năng); ghi chú tay có tiêu đề. Dữ liệu mẫu (giả)."""

from app import db, messenger
from tests.conftest import csrf, dang_nhap
from tests.test_messenger import sheet  # noqa: F401 — fixture Sheet giả


def _giao(c, conn, cid="1001"):
    sale1 = conn.execute("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale1'").fetchone()[0]
    c.post("/lead-moi", data={"csrf": csrf(c, f"/lead-moi?messenger={cid}"), "ten_ph": "Mai Thử", "sdt": "0911000001",
                              "customer_id": cid, "sale_id": str(sale1), "ghi_chu": "Gọi buổi tối"})
    return conn.execute("SELECT id FROM lead WHERE customer_id = ?", (cid,)).fetchone()[0]


def test_ho_so_hien_ghi_chu_bot_va_tu_cap_nhat(sheet):  # noqa: F811
    hang, _ = sheet
    conn = db.ket_noi()
    messenger.dong_bo(conn)  # lúc giao: Sheet chưa có ghi chú bot
    lid = _giao(dang_nhap("chu"), conn)
    s = dang_nhap("sale1")
    trang = s.get(f"/lead/{lid}").text
    assert "Chatbot đã tư vấn" in trang and "Bot chưa có tóm tắt" in trang
    assert "<h3>Ghi chú</h3>" in trang and "Gọi buổi tối" in trang
    hang[0].update(bot_summary="Phụ huynh hỏi học phí; bot đã gửi bảng học phí.", media_sent="Học phí hệ Quốc tế 16/11")
    messenger.dong_bo(conn)  # /ghichucu điền Sheet, app lấy lại
    trang = s.get(f"/lead/{lid}").text
    assert "Phụ huynh hỏi học phí; bot đã gửi bảng học phí." in trang and "Học phí hệ Quốc tế 16/11" in trang
    assert "Bot chưa có tóm tắt" not in trang


def test_lead_khong_tu_messenger_khong_co_khung_bot(du_lieu):
    c = dang_nhap("chu")
    lid = db.ket_noi().execute("SELECT id FROM lead WHERE customer_id = '' LIMIT 1").fetchone()[0]
    assert "Chatbot đã tư vấn" not in c.get(f"/lead/{lid}").text


def test_sale_khac_khong_xem_duoc(sheet):  # noqa: F811
    conn = db.ket_noi()
    messenger.dong_bo(conn)
    lid = _giao(dang_nhap("chu"), conn)
    assert dang_nhap("sale2").get(f"/lead/{lid}").status_code == 404
