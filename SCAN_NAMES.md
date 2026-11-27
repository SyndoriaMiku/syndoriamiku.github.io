# Scan Names — CUDA NER

Both builders now use `gpu_name_scanner.py` for recognition, and
`name_suggestions.py` for API suggestions. The previous rule scanner remains
in `name_scanner.py` but is not the default.

## Install (Python 3.10, NVIDIA)

Run in the Conda environment used to start the builder (for this project, `p310`):

```powershell
conda activate p310
python -m pip install -r requirements-scanner-gpu.txt
python -c "import torch; print(torch.cuda.is_available())"
```

The NVIDIA driver must support CUDA 12.8. No separate CUDA toolkit is needed.
CPU-only users can install `requirements-scanner.txt` instead.

## Bản exe: Moxhi chạy bằng numpy

`dist/StoryStudio.exe` và `dist/StoryTranslatorPro.exe` không kèm torch/transformers (vài GB). Trong exe,
Moxhi chạy bằng `moxhi_numpy.py`: Marian viết lại bằng numpy, đọc thẳng `model.safetensors`, tách từ bằng
sentencepiece. Chỉ CPU, chỉ Moxhi (BERT cần chạy từ source).

- **Kết quả giống bản torch:** trạng thái encoder lệch < 2e-6; 40/40 câu thật sinh đúng từng token (beam 2 và 4);
  quét cả chương ra đúng cùng danh sách tên, số lần và tên Việt. Test: `tests/test_moxhi_numpy.py`.
- **Model:** dùng chung `models/MoxhiMT-30-Tag` ở thư mục gốc repo (exe nằm trong `dist/`). Chưa có thì exe tự
  tải từng file của revision đã ghim từ Hugging Face (không cần `huggingface_hub`).
- Chạy từ source vẫn dùng torch (GPU nếu có). Ép bản numpy để thử: `$env:STV_MOXHI_BACKEND = "numpy"`.
- **Build exe:** `powershell -ExecutionPolicy Bypass -File toolsuild_exe.ps1` (đặt DLL của môi trường lên đầu
  PATH; nếu không exe có thể báo lỗi Tcl lệch phiên bản khi mở).

## Hai bộ quét (mặc định chỉ Moxhi; "both" chạy cả hai rồi gộp)

| Bộ quét | File | Model |
|---|---|---|
| Moxhi | `moxhi_scanner.py` | [DanVP/MoxhiMT-30-Tag](https://huggingface.co/DanVP/MoxhiMT-30-Tag), cùng model với trang moxhi-tag.pages.dev (CC-BY-NC-4.0, phi thương mại) |
| BERT | `gpu_name_scanner.py` | shibing624/bert4ner-base-chinese (Apache 2.0) |

- **Moxhi** là model dịch Trung→Việt 37M tham số, đánh thẻ tên trong bản dịch (`PER`, `LOC`, `ORG`, `ITEM`
  = pháp bảo, đan dược, công pháp…). Một đầu NER nhỏ trên encoder tìm tên trong câu chữ Hán. Mỗi tên được dịch
  trong ngữ cảnh, nên có sẵn **tên tiếng Việt** (cột/nút "Moxhi" trong hộp thoại, F2 xoay vòng Moxhi → Hán-Việt → API).
- **Gộp:** tên cả hai cùng thấy có tín hiệu "BERT + Moxhi cùng thấy" và vào tab *Chắc chắn*. Chữ hư dính mép
  (`和小龙`, `太浩宗内`) được cắt theo bản dịch tiếng Việt hoặc theo tên lõi đã thấy ở chỗ khác.
- **Đo trên 80 chương thử** (tìm lại tên bị giấu khỏi name.cfg): BERT 82%, Moxhi 75%, **gộp 89%**.
  Tên Việt Moxhi khớp name.cfg 90%.
- **Chọn bộ quét:** `"scan_engine": "moxhi"` (mặc định) `| "both" | "bert"` trong `editor_config.json` (file cài
  đặt trên máy, không nằm trong git), hoặc biến môi trường `STV_SCAN_ENGINE`.
- Model Moxhi (≈150 MB, pin revision `c761ea549aa78a7819bd7ba1ace85b3d35b7ee16`) nằm ở `models/MoxhiMT-30-Tag`,
  tự tải lần quét đầu; tải trước bằng `python moxhi_scanner.py`, thử bằng `python moxhi_scanner.py --test`.
  Đổi thư mục bằng `STV_MOXHI_MODEL_DIR`.
- Cần `sentencepiece==0.2.0` (bản mới hơn bỏ `immutable_proto` dùng để lấy vị trí chữ). Code hậu xử lý được viết
  lại theo model card; file `moxhi_tag.py` của repo model không được tải hay chạy.

## Recognition

Model: https://huggingface.co/shibing624/bert4ner-base-chinese (Apache 2.0).
Pinned revision: `5d660ed2aa9da482bf2d99c6bc8cf2ce66758f6a`.
Only safetensors weights are loaded; remote Python code is disabled.

### Local model folder (no re-download)

The model is stored inside the app folder, not the Hugging Face user cache:

```
models/bert4ner-base-chinese/   config.json, vocab.txt, model.safetensors, stv_model.json
```

- Every scan loads straight from this folder with Hugging Face forced offline,
  so no network check or download happens after the first setup.
- First time only: if the model is already in the old Hugging Face cache
  (`%USERPROFILE%\.cache\huggingface`), it is copied into `models/` without
  downloading. Otherwise about 400 MB is downloaded once. An interrupted
  download resumes from `models/bert4ner-base-chinese.partial`.
- `stv_model.json` records the pinned revision; if `REVISION` changes, the
  folder is refreshed automatically.
- The frozen EXE looks for `models/` next to `StoryTranslatorPro.exe`
  (or next to the `dist` folder), the same rule as `name.cfg`.
- To keep the model elsewhere (another drive, shared folder):
  `$env:STV_NER_MODEL_DIR = "D:\AI\bert4ner-base-chinese"`.
- To move it to another PC, copy the whole `models` folder; no internet needed.
- `models/` is in `.gitignore` — never commit it to GitHub Pages.
- If a scan reports a broken model folder, delete it and run the download
  command below again.

When a builder starts and the model is already on disk, it is loaded into
memory in the background, so the first Scan Names does not wait for loading.
Disable with `$env:STV_NER_PRELOAD = "0"`.

Source text is processed locally for recognition; discovered names are sent
to the existing translation API for suggestions.

The scanner recognizes PERSON, PLACE and ORG using Chinese context. It does
not separately classify fantasy skills or items. This model was trained on
news/general Chinese, so fantasy names still require review. Scores are
model confidence, not a guarantee that a candidate is a proper name.
Counts represent detected, deduplicated occurrences. Overlapping token windows
avoid truncating novels.

The candidate filter is recall-first: a name survives down to 55% confidence
(a one-character name needs 90%), may contain digits or Latin letters, and two
spans separated only by a middle dot are joined. A candidate is dropped only
when the occurrence itself sits inside a saved name, so a shorter name that
also appears on its own is still reported. Overlapping spans of different
types are kept; same-type overlaps keep the longer span. Use the "Điểm" filter
in the dialog to trade recall for precision.

### Name dictionary (names.json)

`names.json` next to the app is a mined name dictionary that **snaps spans to
whole phrases**: every dictionary name found in the text is added at its exact
span, and overlaps are resolved longest-span-first (a whole name always beats a
fragment). It only supplements — never removes — NER output, and it never
contains names already in `name.cfg`.

- Build/renew it (GPU, one pass over the corpus):
  `python tools/name_ner/mine.py --out names.json` (defaults: count ≥ 3,
  confidence ≥ 0.85). Only multi-character, name-shaped phrases from ≥ 3
  characters are kept; two-character mining was dominated by common words.
- Delete or rename `names.json` to disable the dictionary; Scan Names still
  works with NER alone.
- Known limits: mining is NER-based, so it adds names the model already finds
  somewhere (good for whole-phrase consistency) but not transliterated foreign
  names; occasional idioms can slip in — raise `--min-count` / `--min-confidence`
  and rebuild for a cleaner, smaller list.

CUDA runs FP16 with small batches. VRAM exhaustion reduces batch size, then
falls back to the same model on CPU. Progress displays the active device.
The GUI and API suggestion rules remain independent of CUDA.
To force a device before launching:

```powershell
$env:STV_NER_DEVICE = "cpu" # auto (default), cpu, cuda
python builder.py
```

To download (or verify) the local model without opening the GUI:

```powershell
conda activate p310
python gpu_name_scanner.py          # download once / check
python gpu_name_scanner.py --test   # also run a small scan
python gpu_name_scanner.py --force  # re-download
```

## Suggestions and review

- Builder (`builder_qt.py` / `builder.py`): normal translation API, no login cookie. Suggestions are
  translations and are not guaranteed to be Sino-Vietnamese readings.
- At most 40 names and 15,000 characters per suggestion batch; a provider
  may impose a smaller character limit. Mismatched responses are retried in
  smaller groups with bounded depth. Transport failures stop further batches.
- Successful suggestions are cached in memory by provider and Chinese name.
  Failed or incomplete readings remain editable and can be retried.
- Nothing is selected for saving by default. Click a Chinese name to inspect
  the evidence and surrounding source text before editing and adding it.

## Reference

https://moxhi.pages.dev/ inspired contextual recognition and separate review
of suggested readings. Its WebGPU r6b model is not included; this application
uses PyTorch CUDA BERT. GPU accelerates recognition, not remote API requests
or Tk text editing. The EXE runs Moxhi only, on CPU, through `moxhi_numpy.py` (see above).

## Local verification

Verified on RTX 3060 Ti with PyTorch 2.8.0+cu128: CUDA inference, CPU inference,
both builder scan wrappers, saved-name exclusion and overlapping-window counts.
A repeated synthetic Chinese sample of 1,053,000 UTF-8 bytes took 18.86 seconds
after model loading; all expected occurrence counts matched. This is a speed
and stitching check, not a real-novel accuracy benchmark. No test files are
stored in the project.
