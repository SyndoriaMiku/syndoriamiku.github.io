# Từ điển tên + bám cụm tên (Hướng B) — Thiết kế

Ngày: 2026-11-12
Trạng thái: đang làm

## Ý định

Nhận diện **đúng cả cụm tên** thay vì cắt vụn/lệch biên. Cách của moxhi: một
từ điển tên + khớp dài nhất, để tên đã biết luôn được bắt trọn cụm. Làm theo,
không đụng model (tránh lại vết xe fine-tune đã fail).

## Cốt lõi

- Scan Names **ẩn** tên đã có trong `name.cfg`, nên giá trị nằm ở **tên khai
  thác** (chưa có trong cfg) mà NER bắt được ở chương này nhưng bỏ ở chương khác.
- **Khai thác**: chạy NER một lượt trên toàn kho (64M ký tự), gộp theo tên với
  `count` + `confidence` cao nhất, giữ tên đủ tần suất + đủ điểm + đúng dạng →
  `names.json`.
- **Bám cụm lúc chạy**: với mỗi chương, khớp dài nhất các tên trong từ điển lên
  text; thêm tên từ điển mà NER bỏ, và kéo biên span NER về đúng cụm từ điển.

## Mục tiêu

- Tăng số cụm tên đúng (span exact) trên bộ eval, so với chỉ-NER.
- Từ điển là văn bản nhỏ, chạy offline, không cần GPU lúc dùng.

## Ngoài phạm vi

- Không train lại model.
- Không xử lý tên phiên âm ngoại quốc (爱丽丝→Alice) — hướng khác.
- Không đổi `name.cfg` hay định dạng `data.json`.

## Ràng buộc

- Giữ `names.json` tách khỏi model; tái tạo được bằng một lệnh.
- Tên khai thác mặc định PERSON (như nhãn yếu đã phân tích).
- Lúc chạy: từ điển chỉ **thêm/kéo biên**, không loại bớt dự đoán NER.

## Rủi ro

- Tên khai thác sai (NER nhầm) sẽ lan ra mọi chương → cần ngưỡng tần suất + điểm
  cao, và luôn có bước người dùng duyệt trong dialog.
- Kho đổi thì từ điển cũ đi → ghi `generated` + lệnh tái tạo.
- Kích thước `names.json` (ước vài trăm KB).

## Kiểm chứng

- Hàm thuần (`aggregate`, `select`, `snap_spans`) có unit test.
- Chạy thật: khai thác → `names.json`; đo lại eval (recall/F1 span) so baseline
  chỉ-NER.
