# Nơi lưu truyện

**Code ở GitHub, truyện ở Cloudflare R2.** Thêm truyện hay chương mới không cần commit, push hay deploy.

| | Ở đâu | Ai ghi |
|---|---|---|
| Code, giao diện trang (HTML/JS/CSS), builder, tools | Git → GitHub Pages | bạn commit/push khi sửa code |
| Truyện: `library/<truyện>/<chương>/data.json`, `stories/<truyện>/data.json`, các danh mục | Thư mục trên máy (bản chính) → R2 | app tự đẩy sau mỗi lần lưu |
| `name.cfg` | Chỉ trên máy | builder |

## Luồng dữ liệu

```
builder/editor lưu truyện ──► library_store.write_catalog() ──► r2_store.request_sync()  (luồng nền)
                                                                     │  so thư mục với .r2_manifest.json
                                                                     ▼  chỉ đẩy/xoá phần chênh lệch
người đọc ──► GitHub Pages (khung trang) ──► Worker stv-data.lyralei2001.workers.dev ──► R2 (bucket stv-library)
```

- **App (`r2_store.py`)**: chương được nén (`data.json.gz`, chữ thường + gzip, ≈ 1/3), danh mục giữ nguyên JSON.
  Chương được đẩy trước, danh mục sau, để trang không trỏ tới chương chưa có. Lỗi mạng: lần đồng bộ sau (hoặc
  lần mở app sau) tự gửi nốt. Xoá hàng loạt (> 50 file và > 5%) bị giữ lại chờ bấm **Xoá file thừa**.
- **Chỉ thư mục của app được đồng bộ**: test hay bản sao repo ở chỗ khác không bao giờ đẩy lên bucket thật.
- **Worker (`cloudflare/worker.js`)**: chỉ đọc. Chương cache 10 phút, danh mục cache 1 phút: truyện/chương mới
  hiện trên web sau ~1 phút; sửa chương cũ thì ≤ 10 phút.
- **Trang web**: không còn file riêng cho từng truyện/chương. `404.html` nạp khung `library/story.html`,
  `library/chapter.html` hoặc `reader.html` ngay tại đường dẫn gốc, nên link, bookmark, tiến độ đọc giữ nguyên.
  `library/assets/chapter-data.js` đọc dữ liệu từ Worker (rồi tới cùng đường dẫn khi chạy trên máy), giải nén.

## Khoá API

App cần một R2 API token (R2 → Manage API tokens → Create: **Object Read & Write**, chỉ bucket `stv-library`).
Dán vào builder → nút **☁ R2** → **Lưu & kiểm tra**. Khoá lưu ở `%APPDATA%\StoryStudio\r2.json`, không nằm
trong repo. Lộ khoá: xoá token trên Cloudflare, tạo token mới, dán lại.

## Việc thường gặp

| Muốn | Làm |
|---|---|
| Đẩy ngay / xem lỗi | ☁ R2 → **Đồng bộ ngay** (hoặc `python r2_store.py`) |
| Đã xoá/chuyển nhiều chương, R2 còn bản cũ | ☁ R2 → **Xoá file thừa** (hoặc `python r2_store.py --allow-delete`) |
| Mất thư mục truyện trên máy | ☁ R2 → **Tải truyện từ R2 về** (hoặc `python r2_store.py --restore`), không cần khoá |
| Xem thử dữ liệu trên máy chưa đồng bộ | chạy `python -m http.server`, đặt `window.CHAPTER_DATA_BASE = ''` trước khi nạp `chapter-data.js` |

## Giới hạn miễn phí

- R2: 10 GB lưu trữ (truyện nén hiện ≈ 250 MB), không tính phí băng thông.
- Worker: 100.000 lượt/ngày. Mỗi lần đọc một chương ≈ 2–3 lượt (chương, danh sách chương, chương sau tải trước).
  Hết lượt thì tới hết ngày không tải được chương, không mất tiền. Đừng nâng lên gói Workers Paid nếu không muốn
  bỏ trần này.
- GitHub Pages: 1 GB — giờ chỉ còn code (≈ 30 MB).
