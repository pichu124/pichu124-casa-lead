# CLAUDE.md

App chăm sóc lead tuyển sinh Casa dei Bambini: FastAPI + SQLite + Jinja, chạy trên VPS của trường (InterData, Việt Nam), cạnh app CASA Mầm non. Đọc `README.md` trước.

## Lệnh

- `./scripts/check.sh`: THE check (cú pháp, chặn dữ liệu thật trong kho, toàn bộ pytest). Chạy trước khi báo xong và trước mỗi commit.
- Môi trường: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`.
- Chạy thử: xem README (dữ liệu mẫu + uvicorn).

## Luật

- `app/quy_tac_nhac.py` là bản chuẩn quy tắc nhắc. Sửa quy tắc: viết test đỏ trong `tests/test_quy_tac_nhac.py` trước, rồi sửa. Không tự tính hạn ở chỗ khác.
- Mọi đường dẫn đọc hay ghi một lead phải đi qua `logic.mot_lead(conn, nguoi, id)` (sale chỉ thấy lead mình phụ trách). Có bài test phân quyền riêng; không nới để cho qua.
- Mọi biểu mẫu POST có mã `csrf`; máy chủ kiểm tra bằng `_bieu_mau`.
- Ô không có nghĩa với tình trạng đã chọn thì máy chủ xoá giá trị trước khi lưu (`_gia_tri_cham_soc`), không dựa vào việc giao diện ẩn ô.
- Lược đồ chỉ thêm: bảng mới `CREATE TABLE IF NOT EXISTS`, cột mới thêm có kiểm tra. Không DROP, không xoá dữ liệu.
- Tin Telegram không chứa SĐT (`telegram.an_sdt` là lớp chặn cuối, đừng bỏ).
- Giao diện và thông báo lỗi bằng tiếng Việt, dễ hiểu cho sale. Ngày hiện dạng dd/mm/yyyy.
- Dữ liệu phụ huynh và trẻ không vào kho mã, log, test hay PR.

## Quyền tự chủ

- Cứ làm: đọc, sửa trên nhánh, commit cục bộ, chạy test, mở PR nháp.
- Luôn hỏi người: push hoặc merge vào `main`, mọi thao tác trên VPS (cài, khởi động lại, sửa Caddy, cron), xoá dữ liệu, gửi tin Telegram thật.
