# Fine-tune NER nhận diện tên (Hướng B) — Thiết kế

Ngày: 2026-11-10
Trạng thái: chờ duyệt (chưa viết code)

## Ý định và lý do

Tính năng Scan Names hiện dùng BERT NER (`gpu_name_scanner.py`,
`shibing624/bert4ner-base-chinese`) train trên tin tức. Người dùng phản hồi
nhận diện **thiếu tên**. Hướng B: tận dụng chính kho truyện đã dịch trong repo
(`library/`, `stories/`) và `name.cfg` để **fine-tune** model sát văn phong
truyện mạng, chạy offline như hiện nay.

Kết quả mong muốn: recall tên cao hơn model gốc, đo được bằng một bộ đánh giá
tách rời theo truyện.

## Dữ liệu hiện có (đo ngày 2026-11-10)

| Nguồn | Quy mô |
|---|---|
| `name.cfg` | 2173 tên (2173 dòng `cn=vi`) |
| `library/` | 310 truyện, 6757 file `data.json`, ~25,04M ký tự Hán; 288.410 lần khớp tên, 1242 key được dùng |
| `stories/` | 444 file `data.json`, ~38,19M ký tự Hán; 331.296 lần khớp tên, 1412 key được dùng |
| Model nền | `models/bert4ner-base-chinese/` (đã có local, ~400MB, Apache-2.0) |

Mọi `data.json` có cặp `cn`/`vi` base64 — đủ để sinh nhãn yếu (weak labels) cho
token là tên.

## Mục tiêu

- Tăng recall nhận diện tên, đo trên tập test **tách theo truyện**.
- Giữ nguyên kiến trúc: torch + BERT token-classification, chạy offline, có
  fallback CPU.
- Tái lập được: một script train + một script đánh giá, chạy trên `p310`.

## Ngoài phạm vi (non-goals)

- Không đổi UI Scan Names hay luồng duyệt tên.
- Không đổi định dạng `name.cfg`, `data.json`, `list.json`.
- Không phụ thuộc mạng khi chạy app.
- Không train từ đầu (chỉ fine-tune từ model nền có sẵn).

## Chống mục tiêu (anti-goals)

- Model phình to hơn nhiều hoặc không còn chạy được trên CPU.
- Precision sụp: đẩy recall bằng cách nhận bừa từ thường là thất bại.
- Kế thừa lỗi bằng self-training vòng lặp không kiểm chứng.

## Ràng buộc

- Giữ nguyên tập nhãn và thứ tự `LABELS` (`gpu_name_scanner.py`) và
  `id2label`, vì `_load()` kiểm tra khớp chính xác.
- Môi trường train: conda `p310`, `torch 2.8.0+cu128`, CUDA khả dụng.
- `models/` nằm trong `.gitignore`; artifact **không** commit lên GitHub Pages.
- App hiện kiểm tra `is_installed()` theo revision đã ghim + `stv_model.json`.

## Rủi ro trọng yếu (phải đọc)

Nhãn yếu lấy từ `name.cfg` chỉ đánh dấu những tên **đã biết**, nhưng Scan Names
cố tình **ẩn** những tên đã có trong `name.cfg`. Nếu fine-tune chỉ học lại phân
bố đó, recall tên **chưa từng thấy** (đúng thứ đang thiếu) có thể **không tăng**.
Vì vậy:

1. Bắt buộc có tập test gồm tên **không** nằm trong `name.cfg`.
2. Chỉ coi là thành công nếu recall trên tập tên-mới tăng mà precision không
   giảm quá một ngưỡng đã định.
3. Nếu không đạt, kết luận trung thực là dữ liệu yếu không đủ, và chuyển sang
   Hướng 2 (pass luật/gazetteer) cho tên mới.

## Các hướng đã cân nhắc

- **B1 — Nhãn yếu từ `name.cfg` + self-training type.** Gán loại (PER/LOC/ORG)
  bằng chính model gốc cho các vị trí khớp, dùng làm nhãn. Rẻ nhưng kế thừa lỗi
  phân loại.
- **B2 — Nhãn yếu từ `name.cfg` + gán loại bằng hậu tố (`han_viet.ENTITY_SUFFIXES`).**
  Minh bạch, tất định; phần lớn còn lại mặc định PERSON. **Chọn B2 làm chính**,
  dùng B1 để kiểm chứng chéo.
- **B3 — Chỉ train 2 lớp name/not-name.** Không tương thích `LABELS`; loại.
- **B4 — Đổi model nền thiên văn học.** Để dành (Hướng C).

## Cách làm đã chốt

- **Nhãn**: BIO token-level cho PER/LOC/ORG. Positive = mọi vị trí của tên trong
  `name.cfg` trên văn bản `cn`.
  - Mặc định PERSON; chỉ nâng thành LOC/ORG khi hậu tố Hán là địa danh/tông môn
    **và** nghĩa Việt trong `name.cfg` có từ khớp (Tông/Môn/Phái/Thành/Đảo…).
  - Hậu tố SKILL/ITEM không có nhãn tương ứng trong `LABELS` → **bỏ khỏi positive**
    (để O), tránh dạy sai loại.
  - Hậu tố chỉ là gợi ý, không phải chân lý: tên người bị hậu tố bắt nhầm
    (vd 林峰, 秦镇海) vẫn về PERSON.
  - Đã đo trên `name.cfg` thật và siết bộ hậu tố: chỉ còn ORG {宗,门,派,教,殿,阁}
    và LOC {岛,湖,谷,界,域}. Loại 国/渊/城/洲/堂/楼/山/河 vì trùng chữ cuối tên
    thật (林建国, 陆渊, 顾城, 沈玉堂, 赵长河, 苏青山). Kết quả: **2168 PER / 3 ORG
    / 0 LOC** — nhãn yếu thực chất là tín hiệu "người vs không", chấp nhận được vì
    mục tiêu là recall tên.
- **Chia tập theo truyện** (story-disjoint): ~80% train, ~10% val, ~10% test.
  Không để cùng truyện xuất hiện ở hai tập. Đơn vị "truyện" = thư mục truyện
  (`library/<slug>` hoặc `stories/<slug>`). Đã kiểm tra `library` và `stories`
  gần như rời nhau (chỉ 10 chương trùng nội dung) — các chương trùng bị loại khỏi
  corpus để tránh rò rỉ.
- **Chồng lấn/chuỗi con**: 169 key của `name.cfg` là chuỗi con của key khác. Luật:
  ưu tiên khớp dài nhất; bỏ key ngắn nằm trọn trong một khớp dài tại cùng vị trí.
- **Đánh giá**: entity-level strict (span + type) precision/recall/F1; báo riêng
  recall trên **tên trong** và **tên ngoài** `name.cfg`; so baseline model gốc
  trên cùng tập.
- **Bộ eval held-out tự động**: tách ngẫu nhiên ~10% tên trong `name.cfg` khỏi
  nhãn train; mọi lần xuất hiện của chúng trong text train được đánh dấu *ignore*
  (không phải O) để không biến chúng thành hard negative; đo recall trên chúng ở
  tập test story-disjoint. Không cần gán tay. Hạn chế: đây vẫn là tên đã được
  curate, chưa phải tên mới hoàn toàn — bộ gán tay bổ sung để sau nếu cần.
- **Class imbalance**: O áp đảo; dùng class weight/focal loss và early-stop theo
  val F1 (tên mới).
- **Tích hợp**: thêm `models/bert4ner-name-vi/`; mở `is_installed()` chấp nhận
  manifest `custom: true` (kèm `base_revision`) mà vẫn kiểm tra đúng label set;
  chọn qua `STV_NER_MODEL_DIR` hoặc hằng số mặc định; giữ fallback CPU.

## Phần để builder tự quyết

- Hyperparameters (lr, batch, epochs, seed), cấu trúc script, cách chia subset
  khi 60M ký tự quá lớn cho một lần train.
- Có dùng gradient accumulation / fp16 hay không.

## Baseline đo được (2026-11-11)

Chạy `tools/name_ner/evaluate.py` với model gốc, 200 chương test, holdout 10%
(217 tên): **recall = 90,8%** (tp 1870 / fn 190 trên 2060 lần xuất hiện).

- Kết luận quan trọng: model gốc đã bắt gần hết tên **kiểu `name.cfg`**. Trần cải
  thiện của Hướng B chỉ còn ~9 điểm recall, phần lớn nằm ở tên không giống
  `name.cfg` (tên mới/tu tiên) — thứ mà nhãn yếu không dạy được.
- **Precision trong lần đo này không có ý nghĩa**: gold chỉ có tên held-out, nên
  dự đoán đúng của 90% tên còn lại bị tính là FP. Muốn đo precision phải có gold
  toàn bộ tên, hoặc đo proxy riêng (tên dự đoán không nằm trong `name.cfg`).
- Hệ quả: lần train đầu là thí nghiệm **có khả năng thất bại**; go/no-go dựa trên
  recall held-out (có ý nghĩa) + chỉ số nhiễu proxy.

## Kết quả go/no-go (2026-11-11)

| Model | recall held-out | tp/fn | dự đoán | precision proxy |
|---|---|---|---|---|
| Gốc (baseline) | **90,8%** | 1870/190 | 55.286 | 3,4% |
| Fine-tune (1 epoch, 20k cửa sổ) | **85,9%** | 1769/291 | 29.756 | 5,9% |

**Kết luận: THẤT BẠI.** Recall giảm ~5 điểm thay vì tăng ≥5; model fine-tune
còn kém nhạy hơn model gốc (dự đoán ít đi gần một nửa). Đúng như dự đoán: nhãn
yếu từ `name.cfg` chỉ dạy lại tên đã biết, không mở rộng sang tên ngoài phân bố,
và một epoch đã kéo lệch model gốc.

**Quyết định:**
- **Không** đổi model mặc định; app tiếp tục dùng model gốc. Hướng 1 (nới lọc)
  vẫn là cải thiện đang dùng.
- Việc còn lại để tăng recall **tên mới** là **Hướng 2** (pass luật/gazetteer
  không jieba), không phải fine-tune.
- Hạ tầng train/eval giữ lại (`tools/name_ner/`) để tái dùng nếu sau này có nhãn
  tay cho tên mới.

## Tiêu chí thành công (đề xuất, cần chốt)

Trên tập test story-disjoint (entity-level strict, so cùng tập với model gốc):
- Recall tên **ngoài** `name.cfg` ≥ baseline + 5 điểm (tuyệt đối).
- Precision ≥ baseline − 3 điểm (không đánh đổi bằng cách nhận bừa).
- Early-stop theo F1 trên val, ưu tiên tên ngoài cfg.
Không đạt → kết luận dữ liệu yếu không đủ và chuyển Hướng 2.

## Đã chốt (2026-11-10, người dùng giao tự quyết)

1. **Mục tiêu = tên chưa từng thấy** (ngoài `name.cfg`) — đúng thứ Scan Names
   đang thiếu. Vì nhãn yếu chỉ đánh dấu tên đã biết, lần train đầu là **thí
   nghiệm có cổng go/no-go**; không đạt thì chuyển Hướng 2 (pass luật/gazetteer).
2. Giữ tiêu chí thành công đã đề xuất (recall ngoài-cfg ≥ baseline +5đ, precision
   ≥ baseline −3đ, early-stop val F1).
3. Artifact = chỉ trọng số fine-tune (~400MB), để trong `models/` (gitignored),
   fp16, một lần train mục tiêu ≤ ~2 giờ; **không** đóng vào exe mặc định.
4. Bộ eval: dùng **held-out tên tự động** (tách ~10% `name.cfg` khỏi nhãn train,
   ignore các lần xuất hiện), không cần người gán tay. Bộ eval là **cổng chặn**:
   phải đo được baseline trước khi train.
