# Dung lượng truyện và nơi lưu dữ liệu chương

GitHub Pages giới hạn **1 GB** cho mỗi trang. Vượt mức này thì bước deploy báo
`Deployment failed, try again later` (không nói rõ nguyên nhân).

## Tổng quan

Repo git luôn là **bản gốc đầy đủ** (`data.json` base64). Builder, editor, studio và trình sửa trên web
chỉ làm việc với repo. Mỗi lần push, workflow `pages.yml` chạy `tools/build_site.py` để dựng bản deploy:

| | Repo | Bản deploy |
|---|---|---|
| Dữ liệu chương | `data.json`, base64 | `data.json.gz`: chữ thường có tiền tố `~`, nén gzip (≈ 1/3) |
| File dev (exe, `.py`, test, `name.cfg`…) | có | không |

Dữ liệu chương nằm ở **một trong hai nơi**, chọn bằng biến `DATA_BASE` trên GitHub:

- **Chưa đặt `DATA_BASE`:** `data.json.gz` nằm luôn trên GitHub Pages (khoảng 280 MB, tháng 11/2026).
- **Đã đặt `DATA_BASE`:** `data.json.gz` nằm trên Cloudflare R2 và được phục vụ qua Worker
  `cloudflare/worker.js`. Pages chỉ còn HTML, JS và danh mục (khoảng 31 MB). R2 miễn phí tới 10 GB.

Trong trình duyệt, `library/assets/chapter-data.js` lần lượt thử Worker → `.gz` trên Pages → `data.json`.
Nhờ vậy trang không hỏng trong lúc chuyển đổi và vẫn đọc được khi chạy thẳng từ repo. Bộ tải cũng giải
nén (dùng `DecompressionStream`, trình duyệt cũ thì nạp pako), tải trước chương sau, và shim `atob`
để mọi trình đọc cũ hiểu chuỗi `~chữ`.

Log Actions in dung lượng mỗi lần deploy, cảnh báo từ 800 MB và dừng hẳn nếu vượt 1000 MB.

## Thiết lập R2 + Worker (làm một lần)

> Không dán khoá API vào chat, issue hay file trong repo — chỉ dán vào GitHub Secrets.

**Cloudflare** (dash.cloudflare.com)
1. **Storage & databases → R2 Object Storage**, bật R2 (cần thêm thẻ hoặc PayPal; miễn phí trong hạn mức).
2. **Create bucket**, ví dụ `stv-library`. **Không** bật Public access / r2.dev.
3. Ở trang R2 Object Storage, **Manage API tokens → Create API token**:
   - quyền **Object Read & Write**, phạm vi **chỉ bucket này**;
   - lưu lại Access Key ID, Secret Access Key và Account ID.
4. **Compute → Workers & Pages → Create → Worker**, đặt tên ví dụ `stv-data` → Deploy, rồi:
   - **Edit code**: dán toàn bộ `cloudflare/worker.js` → Deploy;
   - **Settings → Bindings → Add → R2 bucket**: tên biến `BUCKET`, chọn bucket ở bước 2.
5. Ghi lại địa chỉ Worker: `https://stv-data.<tên>.workers.dev`.

**GitHub** (repo → Settings → Secrets and variables → Actions)
1. **Secrets:** `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
2. **Variables:** `R2_BUCKET` (ví dụ `stv-library`).
3. Chạy workflow **Deploy GitHub Pages** (tab Actions → Run workflow). Bước "Sync chapter data to R2"
   tải toàn bộ dữ liệu lên R2; lúc này trang vẫn đọc từ Pages.
4. Kiểm tra `https://stv-data.<tên>.workers.dev/library/<truyện>/<chương>/data.json.gz` trả về file.
5. **Bật:** thêm biến `DATA_BASE` = địa chỉ Worker (không có `/` ở cuối), rồi chạy lại workflow.

**Quay lại cách cũ:** xoá biến `DATA_BASE` rồi chạy lại workflow; dữ liệu lại nằm trên Pages.

## Vận hành

- Mỗi lần push chỉ những chương thay đổi được tải lên R2 (`rclone copy --checksum`).
- Chương bị xoá hoặc chuyển khỏi repo vẫn còn trên R2. Muốn dọn thì chạy tay workflow và tích
  **prune** (`rclone sync`).
- Worker miễn phí 100.000 lượt mỗi ngày; mỗi lần mở chương tốn khoảng 2 lượt (chương đó và chương sau).
- Worker chỉ cho đọc `library/*/*/data.json.gz` và `stories/*/data.json.gz`, và chỉ trả CORS cho
  `syndoriamiku.github.io` cùng localhost.
- Lộ khoá API: xoá khoá trên Cloudflare, tạo khoá mới, rồi cập nhật GitHub Secrets.

Chạy thử trên máy:

```
python tools/build_site.py                      # dữ liệu nằm trong _site
python tools/build_site.py _site --data-dir _data --data-base https://stv-data.<tên>.workers.dev
python -m http.server -d _site
```
