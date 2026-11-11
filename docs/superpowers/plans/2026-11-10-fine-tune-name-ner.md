# Fine-tune NER nhận diện tên — Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fine-tune model NER hiện có bằng nhãn yếu sinh từ `name.cfg` + kho truyện trong repo, đo trên tập tên chưa từng thấy, rồi tích hợp vào Scan Names nếu vượt cổng go/no-go.

**Architecture:** Tách toàn bộ logic dữ liệu/nhãn/đo lường thành package thuần Python (`tools/name_ner/`, test được không cần torch). Script train/eval dùng torch/transformers chạy trên `p310`. App chỉ thêm cơ chế chọn model qua manifest `custom`.

**Tech Stack:** Python 3.10 (`p310`), torch 2.8.0+cu128, transformers, `unittest` (repo đang dùng), model nền `shibing624/bert4ner-base-chinese`.

**Spec:** `docs/superpowers/specs/2026-11-10-fine-tune-name-ner-design.md`

## Global Constraints

- Giữ nguyên tập nhãn và thứ tự `LABELS` trong `gpu_name_scanner.py`; model fine-tune phải có `id2label` khớp.
- Chạy offline khi dùng app; train chỉ trên máy có GPU, artifact để trong `models/` (đã gitignored).
- Chia tập **theo truyện**, `library` và `stories` gộp chung một danh sách truyện; loại chương trùng nội dung.
- Nhãn yếu: mặc định PERSON; LOC/ORG chỉ khi hậu tố Hán + nghĩa Việt cùng khớp; SKILL/ITEM bỏ khỏi positive; ưu tiên khớp dài nhất.
- Tiêu chí go/no-go: recall tên ngoài `name.cfg` ≥ baseline +5 điểm; precision ≥ baseline −3 điểm.
- Test chạy bằng `python -m unittest discover -s tests`; giữ output sạch.

## Review Focus

- `name.cfg` chứa key trùng, key rỗng, vi rỗng, vi chứa '=' → loader phải bỏ qua chứ không crash.
- Chương có `cn` rỗng hoặc base64 hỏng → bỏ qua, không làm gãy corpus.
- Key là chuỗi con của key khác (169 trường hợp) → khớp dài nhất, không gán 2 nhãn chồng.
- Chương trùng nội dung giữa `library` và `stories` → phải loại để không rò rỉ train/test.
- Model fine-tune sai thứ tự nhãn → app phải từ chối nạp, không dự đoán loại sai.

---

### Task 1: Đọc corpus + khử trùng chương

**Files:** Create `tools/name_ner/__init__.py`, `tools/name_ner/corpus.py`; Test `tests/test_name_ner_corpus.py`.

**Interfaces:**
- Produces: `Chapter = namedtuple("Chapter", "story slug path cn")`; `iter_chapters(library_dir, stories_dir) -> list[Chapter]`; `dedupe(chapters) -> list[Chapter]` (bỏ chương có md5 `cn` đã gặp).

- [ ] Bước 1: viết test thất bại — dựng `library/<story>/<chap>/data.json`, `stories/<slug>/data.json` tạm; `iter_chapters` trả `cn` đã giải base64 và nối các đoạn bằng `\n`; `dedupe` giữ bản đầu khi 2 chương cùng nội dung.
- [ ] Bước 2: `python -m unittest tests.test_name_ner_corpus -v` → FAIL `no attribute iter_chapters`.
- [ ] Bước 3: cài đặt `corpus.py` (bỏ qua file lỗi/`cn` rỗng; `story` = thư mục mức 1).
- [ ] Bước 4: chạy lại → PASS.
- [ ] Bước 5: commit.

### Task 2: Chia tập theo truyện

**Files:** `tools/name_ner/corpus.py`; Test `tests/test_name_ner_corpus.py`.

**Interfaces:** `split_stories(story_ids, ratios=(0.8,0.1,0.1), seed=0) -> dict[str, list[str]]` khóa `train/val/test`.

- [ ] Test: rời nhau, hợp đủ, chạy 2 lần cùng seed ra cùng kết quả, tỉ lệ xấp xỉ.
- [ ] Chạy test → FAIL; cài `split_stories` (sort rồi `random.Random(seed).shuffle`); chạy → PASS; commit.

### Task 3: Bảng loại tên từ name.cfg

**Files:** `tools/name_ner/labels.py`; Test `tests/test_name_ner_labels.py`.

**Interfaces:** `load_name_types(name_cfg_path) -> dict[str, str]` với giá trị `PER|LOC|ORG|IGNORE`.

- [ ] Test: dòng `某某=Tên` → `PER`; `青云宗=Thanh Vân Tông` → `ORG`; `某某城=... Thành` → `LOC`; `某诀=... Quyết` → `IGNORE`; `林峰=Lâm Phong` → `PER`; dòng rỗng/`#`/không `=` bị bỏ.
- [ ] Chạy → FAIL; cài đặt (dùng `han_viet.ENTITY_SUFFIXES` + `han_viet.COMMON`? không — chỉ suffix + từ khóa trong vi); chạy → PASS; commit.

### Task 4: Gán BIO nhãn yếu (khớp dài nhất)

**Files:** `tools/name_ner/labels.py`; Test `tests/test_name_ner_labels.py`.

**Interfaces:** `weak_spans(text, types) -> list[tuple[int,int,str]]` (không chồng, bỏ `IGNORE`).

- [ ] Test: `types={"上官":"PER","上官婉兮":"PER"}` + text `上官婉兮` → chỉ `(0,4,"PER")`; hai key chồng khác vị trí giữ cả hai; `IGNORE` không xuất hiện.
- [ ] Chạy → FAIL; cài đặt (quét theo độ dài giảm dần, đánh dấu vùng đã chiếm); chạy → PASS; commit.

### Task 5: Metric entity-level

**Files:** `tools/name_ner/metrics.py`; Test `tests/test_name_ner_metrics.py`.

**Interfaces:** `prf(gold: set, pred: set) -> dict` khóa `precision/recall/f1/tp/fp/fn`; span là `(start,end,type)`.

- [ ] Test: trùng khớp hoàn hảo; thiếu 1 (fn); thừa 1 (fp); đúng span sai type = cả fp lẫn fn; mẫu số 0 → 0.0.
- [ ] Chạy → FAIL; cài đặt; chạy → PASS; commit.

### Task 6: Bộ eval tên-mới (sinh + duyệt)

**Files:** `tools/name_ner/eval_set.py`; Test `tests/test_name_ner_eval_set.py`.

**Interfaces:** `candidate_rows(spans, types, known) -> list[dict]`; `gold_from_rows(rows, decisions) -> list[tuple[int,int,str]]`.

- [ ] Test: ứng viên nằm trong `known` bị loại; `decisions` giữ/bỏ đúng; kết quả là tập span.
- [ ] Chạy → FAIL; cài đặt; chạy → PASS; commit.
- [ ] Sinh danh sách ứng viên từ vài chương giữ riêng (chạy script một lần trên `p310`), người dùng duyệt → lưu `docs/superpowers/specs/eval-gold-*.json` (không thuộc repo code).

### Task 7: Đo baseline

**Files:** `tools/name_ner/evaluate.py`.

- [ ] Cài `evaluate.py`: nạp gold, chạy `gpu_name_scanner.NameScanner` (model hiện tại) trên chương eval, quy span dự đoán về `(start,end,type)`, in JSON metric.
- [ ] Chạy trên `p310` với gold vừa duyệt; lưu `baseline.json`. Đây là **mốc so sánh**.
- [ ] Commit script.

### Task 8: Script train

**Files:** `tools/name_ner/dataset.py`, `tools/name_ner/train.py`; Test `tests/test_name_ner_dataset.py` (dùng tokenizer giả).

**Interfaces:** `bio_example(cn, tokenizer, types, max_len) -> dict` với `input_ids/attention_mask/labels`; `train.py --out models/bert4ner-name-vi`.

- [ ] Test dataset: tokenizer giả trả offset ký tự; nhãn O cho token ngoài span; cắt theo `max_len` không làm lệch nhãn.
- [ ] Chạy → FAIL; cài đặt; chạy → PASS; commit.
- [ ] Cài `train.py`: story-disjoint split, class weight cho O, fp16, early-stop theo entity-F1 val (ưu tiên tên ngoài cfg), lưu trọng số + `stv_model.json` kiểu `custom`.
- [ ] Chạy một lần giới hạn (subset/epoch nhỏ) để xác nhận lưu/nạp được; ghi lệnh đầy đủ vào doc.

### Task 9: Tích hợp chọn model custom

**Files:** Modify `gpu_name_scanner.py`; Test `tests/test_name_ner_integration.py`.

**Interfaces:** `is_installed(path)` chấp nhận manifest base **hoặc** custom; `custom_manifest(path) -> bool`.

- [ ] Test: manifest `{"custom": true, "base_revision": ...}` + đủ file + vocab → `is_installed` True; thiếu tokenizer → False; manifest base cũ vẫn True.
- [ ] Chạy → FAIL; cài đặt (không phá đường base); chạy → PASS; commit.

### Task 10: Go/no-go + tài liệu

- [ ] Chạy `evaluate.py` với model fine-tune; so `baseline.json`.
- [ ] Nếu đạt tiêu chí: cập nhật `SCAN_NAMES.md` (cách train, chọn model, cảnh báo) và mặc định dùng model mới.
- [ ] Nếu không đạt: ghi kết luận vào spec và đề xuất chuyển Hướng 2; **không** đổi mặc định.

## Self-review

- Phủ spec: corpus/dedup (T1), split (T2), loại nhãn (T3), BIO (T4), metric (T5), eval (T6-7), train (T8), tích hợp (T9), go/no-go + docs (T10). Không sót mục nào.
- Kiểu/tên thống nhất: `load_name_types` → `weak_spans` → `bio_example` → metric span `(start,end,type)`; `is_installed/custom_manifest` khớp T9.
- Review Focus đã gắn test: T1 (corpus hỏng), T3 (cfg bẩn), T4 (chuỗi con), T1 (trùng chương), T9 (sai nhãn).
