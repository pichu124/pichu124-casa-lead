# Cài app chăm sóc lead lên VPS của trường

Máy: VPS InterData đặt tại Việt Nam, IP `103.195.238.114`, Ubuntu 24.04, giờ máy +07, người dùng `casa`. Trên máy đã có app CASA Mầm non (`/opt/casa-mamnon`, cổng 3000, Caddy lo HTTPS). App chăm sóc lead chạy **bên cạnh**, không đụng gì của app kia:

| | CASA Mầm non (đã có) | Chăm sóc lead (mới) |
|---|---|---|
| Mã | `/opt/casa-mamnon` | `/opt/casa-lead` |
| Dữ liệu | `/var/lib/casa-mamnon` | `/var/lib/casa-lead` |
| Dịch vụ | `casa-mamnon` | `casa-lead` |
| Cổng (chỉ trong máy) | 3000 | 8100 |
| Tên miền | `casa-school.duckdns.org` | `casa-lead.duckdns.org` (tạm, miễn phí) |

Chỗ chung duy nhất là Caddy. Tệp `/etc/caddy/Caddyfile` có dòng `import /etc/caddy/sites/*.caddy`, nên app này có **tệp riêng** `/etc/caddy/sites/casa-lead.caddy`; không sửa tệp chính, không đụng `casa-website.caddy`.

**Cách làm:** đăng nhập máy bằng `ssh casa@103.195.238.114`, rồi **dán từng dòng một**, chờ dấu nhắc hiện lại rồi mới dán dòng tiếp. Dán cả khối một lúc dễ hỏng mà không báo lỗi.

## 0. Chuẩn bị (làm trên điện thoại hoặc máy tính, không cần vào VPS)

1. **Bot Telegram riêng cho app**: trong Telegram nhắn `@BotFather` → `/newbot` → đặt tên (vd `Casa nhắc lead`) và username (vd `casa_lead_bot`). Giữ lại **token** (dạng `123456:ABC…`). Token là bí mật: không gửi vào nhóm chat, không dán vào kho mã.
2. **Tên miền tạm**: vào https://www.duckdns.org bằng tài khoản đã tạo `casa-school`, thêm tên `casa-lead`, ô "current ip" điền `103.195.238.114`, bấm **update ip**.

## 1. Cài Python và lấy mã

```bash
sudo apt-get update
sudo apt-get install -y python3-venv git sqlite3
python3 --version
```

Dòng cuối phải in `Python 3.12` trở lên.

Kho mã là `pichu124/pichu124-casa-lead`. Máy dùng một **khoá chỉ đọc** (deploy key) để kéo mã, nên vẫn chạy được nếu sau này chuyển kho sang riêng tư:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/casa-lead-deploy -C "vps casa-lead"
cat ~/.ssh/casa-lead-deploy.pub
```

Chép dòng in ra. Trên GitHub mở kho `pichu124-casa-lead` → **Settings → Deploy keys → Add deploy key**, dán vào, **không** tick "Allow write access", bấm **Add key**. Rồi trên VPS:

```bash
printf 'Host github-casa-lead\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/casa-lead-deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
sudo mkdir -p /opt/casa-lead /var/lib/casa-lead
sudo chown casa:casa /opt/casa-lead /var/lib/casa-lead
chmod 700 /var/lib/casa-lead
git clone git@github-casa-lead:pichu124/pichu124-casa-lead.git /opt/casa-lead
cd /opt/casa-lead
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
./scripts/check.sh
```

Dòng cuối phải in `check.sh XANH`. Máy chỉ lấy nhánh `main`.

## 2. Cấu hình và tài khoản chủ

Tệp cấu hình chứa token Telegram, chỉ `root` và `casa` đọc được:

```bash
sudo install -m 640 -o root -g casa /dev/null /etc/casa-lead.env
sudo nano /etc/casa-lead.env
```

Gõ vào (thay `<…>`), lưu bằng Ctrl+O, Enter, thoát Ctrl+X:

```
CASA_LEAD_ENV=production
CASA_LEAD_DATA=/var/lib/casa-lead
CASA_LEAD_URL=https://casa-lead.duckdns.org
TELEGRAM_BOT_TOKEN=<token BotFather đưa>
TELEGRAM_BOT_USERNAME=<username của bot, không có @>
```

Tạo tài khoản chủ **trước khi bật dịch vụ** (mật khẩu được hỏi ở dòng lệnh, không hiện ra):

```bash
cd /opt/casa-lead
CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/tao_tai_khoan.py <tên đăng nhập> "<Tên chủ>"
```

Thử sao lưu một lần ngay, khi chưa có dữ liệu:

```bash
CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/sao_luu.py
```

## 3. Dịch vụ tự bật lại

`--host 127.0.0.1`: app chỉ nghe trong máy; Caddy là cửa duy nhất ra Internet (tường lửa `ufw` cũng chỉ mở 22/80/443).

```bash
sudo tee /etc/systemd/system/casa-lead.service >/dev/null <<'UNIT'
[Unit]
Description=Casa cham soc lead
After=network.target

[Service]
Type=simple
User=casa
WorkingDirectory=/opt/casa-lead
EnvironmentFile=/etc/casa-lead.env
ExecStart=/opt/casa-lead/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now casa-lead
curl -s http://127.0.0.1:8100/healthz; echo
```

Dòng cuối phải in `ok`. Không ra thì xem lỗi: `sudo journalctl -u casa-lead -n 50`.

## 4. HTTPS qua Caddy

Kiểm tra tên miền đã trỏ đúng máy (phải in `103.195.238.114  casa-lead.duckdns.org`):

```bash
getent hosts casa-lead.duckdns.org
```

Tạo tệp riêng cho app, từng dòng một (dòng dài dán vào dễ bị ngắt):

```bash
echo 'casa-lead.duckdns.org {' | sudo tee /etc/caddy/sites/casa-lead.caddy
echo '    encode zstd gzip' | sudo tee -a /etc/caddy/sites/casa-lead.caddy
echo '    reverse_proxy 127.0.0.1:8100' | sudo tee -a /etc/caddy/sites/casa-lead.caddy
echo '}' | sudo tee -a /etc/caddy/sites/casa-lead.caddy
sudo caddy validate --config /etc/caddy/Caddyfile
```

Chỉ khi thấy `Valid configuration` mới nạp lại:

```bash
sudo systemctl reload caddy
curl -s https://casa-lead.duckdns.org/healthz; echo
curl -sI https://casa-school.duckdns.org | head -1
```

Dòng đầu phải in `ok` (lần đầu chờ khoảng 1 phút để Caddy xin chứng chỉ); dòng sau kiểm app CASA Mầm non vẫn chạy.

Lỡ hỏng: `sudo rm /etc/caddy/sites/casa-lead.caddy && sudo systemctl reload caddy`.

## 5. Sao lưu ra Google Drive (mã hoá) và lịch chạy hằng ngày

Bản sao lưu trong `/var/lib/casa-lead/backups` nằm cùng ổ với dữ liệu gốc. Mỗi đêm máy đẩy thêm một bản **đã mã hoá** lên Google Drive của trường bằng `rclone`; Google và người mở Drive chỉ thấy tệp tên lạ.

**5a. Nối Google Drive** (`rclone config` trên VPS, đăng nhập Google trên một máy có trình duyệt):

```bash
sudo apt-get install -y rclone
rclone config
```

Trả lời: `n` → name `gdrive` → Storage `drive` → client_id, client_secret để trống → scope `3` (`drive.file`: rclone chỉ thấy tệp nó tạo) → service_account_file trống → advanced `n` → auto config **`n`**. Máy in lệnh `rclone authorize "drive" "…"`: chạy lệnh đó trên laptop (Windows: tải rclone ở rclone.org/downloads, giải nén, `.\rclone.exe authorize …`), đăng nhập Gmail của trường, cho phép, chép đoạn giữa `--->` và `<---End paste` dán vào VPS (đoạn này là chìa khoá Drive, không gửi ai, không cần lưu). Shared Drive `n` → `y` → `q`.

```bash
rclone mkdir gdrive:casa-sao-luu
rclone lsd gdrive:
```

**5b. Lớp mã hoá** (`rclone config` lần nữa): `n` → name `mahoa` → Storage `crypt` → remote `gdrive:casa-sao-luu` → hai câu tiếp Enter → mật khẩu `g`, Bits Enter.

> **Mật khẩu mã hoá phải lưu ở ít nhất hai nơi ngoài VPS** (trình quản lý mật khẩu, giấy trong két). Mất nó thì mọi bản trên Drive không mở được. Không gửi qua chat.

Rồi `y` → mật khẩu thứ hai (salt) `n` → advanced `n` → `y` → `q`. Thử:

```bash
echo "thu" > /tmp/thu.txt && rclone copy /tmp/thu.txt mahoa: && rclone cat mahoa:thu.txt
rclone ls gdrive:casa-sao-luu
rclone delete mahoa:thu.txt && rm /tmp/thu.txt
```

Qua `mahoa:` đọc được `thu`; trên `gdrive:` chỉ thấy tên đã mã hoá.

**5c. Lịch chạy** (giữ nguyên dòng sao lưu 02:00 của CASA Mầm non). Dán từng lệnh, mỗi lệnh một dòng:

```bash
crontab -l > ~/crontab-truoc-casa-lead.txt
(crontab -l; echo '15 2 * * * cd /opt/casa-lead && CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/sao_luu.py >> /home/casa/sao-luu-lead.log 2>&1 && rclone copy /var/lib/casa-lead/backups mahoa:casa-lead >> /home/casa/sao-luu-lead.log 2>&1') | crontab -
(crontab -l; echo '0 8 * * 1-5 cd /opt/casa-lead && set -a && . /etc/casa-lead.env && set +a && .venv/bin/python -m app.nhac_sang >> /home/casa/nhac-sang.log 2>&1') | crontab -
(crontab -l; echo '*/5 7-21 * * * cd /opt/casa-lead && set -a && . /etc/casa-lead.env && set +a && .venv/bin/python -m app.dong_bo_messenger >> /home/casa/messenger.log 2>&1') | crontab -
(crontab -l; echo '5 7 * * * cd /opt/casa-lead && set -a && . /etc/casa-lead.env && set +a && .venv/bin/python -m app.kiem_tra_sao_luu >> /home/casa/kiem-tra-sao-luu.log 2>&1') | crontab -
crontab -l
```

Dòng 1: 02:15 mỗi đêm sao lưu, kiểm tra bản sao, dọn bản cũ (giữ mọi bản 2 ngày, mỗi ngày một bản trong 14 ngày, mỗi tháng một bản trong 12 tháng), rồi đẩy lên Drive. `rclone copy` chỉ thêm, **không bao giờ xoá trên Drive**: VPS bị phá thì bản trên Drive vẫn còn. Dòng 2: tin nhắc 8:00 thứ 2 – thứ 6 (app tự bỏ ngày lễ trong mục Ngày nghỉ). Dòng 3: mỗi 5 phút từ 7:00 tới 21:55, mọi ngày, lấy tab Leads của bot Messenger về app và báo vào nhóm Telegram (chưa nối nhóm thì báo riêng cho chủ) khi có phụ huynh mới để SĐT chờ giao sale; mỗi người báo một lần, lần chạy đầu chỉ ghi nhớ. Dòng 4: 7:05 mỗi sáng kiểm bản sao lưu đêm qua của casa-lead và CASA Mầm non có trên VPS và trên Drive (`rclone lsf mahoa:…`); thiếu thì báo nhóm Telegram (chưa nối nhóm thì chủ), đủ thì im lặng. Chạy thử: `.venv/bin/python -m app.kiem_tra_sao_luu --thu`.

Chạy thử ngay:

```bash
cd /opt/casa-lead && CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/sao_luu.py && rclone copy /var/lib/casa-lead/backups mahoa:casa-lead
rclone ls mahoa:casa-lead
set -a && . /etc/casa-lead.env && set +a && .venv/bin/python -m app.nhac_sang --thu
```

**CASA Mầm non dùng chung lớp mã hoá này** (cùng mật khẩu, thư mục `casa-mamnon`): dòng cron 02:00 của app đó được nối thêm `; rclone copy /var/lib/casa-mamnon/backups mahoa:casa-mamnon >> /home/casa/backup-casa.log 2>&1`. Đã thử khôi phục bằng mật khẩu đã lưu trên một máy khác (16/11/2026): đạt.

**Lấy lại dữ liệu từ Drive** (VPS mới hoặc máy khác): cài rclone, tạo lại `gdrive` và `mahoa` như trên với **đúng mật khẩu đã lưu** (mật khẩu thứ hai vẫn để trống), rồi:

```bash
rclone ls mahoa:casa-lead
rclone copy mahoa:casa-lead/<tên bản muốn lấy> /tmp/khoi-phuc/
sudo systemctl stop casa-lead
mv /var/lib/casa-lead/casa-lead.db /var/lib/casa-lead/casa-lead.db.cu 2>/dev/null; rm -f /var/lib/casa-lead/casa-lead.db-wal /var/lib/casa-lead/casa-lead.db-shm
cp /tmp/khoi-phuc/<tên bản> /var/lib/casa-lead/casa-lead.db && chmod 600 /var/lib/casa-lead/casa-lead.db
sudo systemctl start casa-lead
```

## 5b. Đọc lead Messenger từ Sheet của bot

App đọc tab `Leads` qua chính web app Apps Script mà bot dùng để ghi, bằng một **token đọc riêng** (token ghi của bot không đọc được). Không cần Google Cloud.

1. Trong Apps Script của Sheet: dán script mới và thêm Script Property `LEADS_READ_TOKEN`, theo repo bot `docs/google-sheet-leads.md` **mục 9**. Deploy **New version** (URL web app giữ nguyên).
2. Trên VPS, thêm hai dòng vào `/etc/casa-lead.env` (`sudo nano /etc/casa-lead.env`):

   ```
   LEADS_SHEET_WEBHOOK_URL=<URL web app, giống biến cùng tên của bot trên Render>
   LEADS_READ_TOKEN=<đúng chuỗi đã đặt cho LEADS_READ_TOKEN ở bước 1>
   ```

3. `sudo systemctl restart casa-lead`, mở **Quản trị → Messenger chưa nhận**: phải thấy các phụ huynh đã để SĐT cho bot. Lỗi thì màn hình in lý do (sai token, script cũ…).

App lấy lại tab Leads mỗi 5 phút từ 7:00 tới 21:55 (cron `app.dong_bo_messenger`, mục 5c, kèm tin báo phụ huynh mới chờ giao), mỗi khi chủ mở màn này (cách nhau ít nhất 1 phút) và trước tin nhắc 8:00. Không ghi gì vào Sheet.

## 6. Dùng thử

Mở https://casa-lead.duckdns.org trên điện thoại, đăng nhập tài khoản chủ.

1. **Tài khoản → Nối Telegram**, làm theo 3 bước trên màn hình.
2. **Quản trị**: tạo tài khoản cho từng sale (tên đăng nhập không dấu, mật khẩu ban đầu ít nhất 8 ký tự), gửi cho họ, dặn đổi lại ở mục Tài khoản và nối Telegram.
3. Trên điện thoại: menu trình duyệt → **Thêm vào màn hình chính** để mở như một app.

## Cập nhật mã về sau

**Lệnh tắt (khuyên dùng).** Làm một lần, chép script ra ngoài kho mã (git pull mà sửa đúng tệp đang chạy thì bash đọc
hỏng):

```bash
cp /opt/casa-lead/scripts/cap-nhat-vps.sh ~/cap-nhat-lead.sh && chmod +x ~/cap-nhat-lead.sh
```

Từ đó mỗi lần chỉ cần `~/cap-nhat-lead.sh`, đứng ở thư mục nào cũng được (script tự vào `/opt/casa-lead`). Script ghi
lại bản đang chạy, sao lưu, `git pull`, cài thư viện nếu `requirements` đổi, chạy `check.sh` (đỏ thì dừng, không khởi
động lại), khởi động lại và kiểm `/healthz`. Script báo khi chính nó có bản mới để chép lại.

Làm tay từng bước (giống hệt lệnh tắt):

```bash
cd /opt/casa-lead
CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/sao_luu.py
git pull
.venv/bin/pip install -r requirements-dev.txt
./scripts/check.sh
sudo systemctl restart casa-lead
curl -s http://127.0.0.1:8100/healthz
```
