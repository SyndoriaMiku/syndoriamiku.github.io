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

## Recognition

Model: https://huggingface.co/shibing624/bert4ner-base-chinese (Apache 2.0).
Pinned revision: `5d660ed2aa9da482bf2d99c6bc8cf2ce66758f6a`.
Only safetensors weights are loaded; remote Python code is disabled.
The first scan downloads about 400 MB to the Hugging Face user cache,
outside the repository. Later scans reuse the local files and the in-memory
model. Source text is processed locally for recognition; discovered names
are sent to the existing translation API for suggestions.

The scanner recognizes PERSON, PLACE and ORG using Chinese context. It does
not separately classify fantasy skills or items. This model was trained on
news/general Chinese, so fantasy names still require review. Scores are
model confidence, not a guarantee that a candidate is a proper name.
Counts represent detected, deduplicated occurrences. Saved names and their
fragments are excluded. Overlapping token windows avoid truncating novels.

CUDA runs FP16 with small batches. VRAM exhaustion reduces batch size, then
falls back to the same model on CPU. Progress displays the active device.
The GUI and API suggestion rules remain independent of CUDA.
To force a device before launching:

```powershell
$env:STV_NER_DEVICE = "cpu" # auto (default), cpu, cuda
python builder.py
```

To download/cache the model without opening the GUI:

```powershell
conda activate p310
python -c "from gpu_name_scanner import NameScanner; print(len(NameScanner().scan('王宏伟来自北京。')))"
```

## Suggestions and review

- `builder.py`: normal translation API, no login cookie. Suggestions are
  translations and are not guaranteed to be Sino-Vietnamese readings.
- `builder_new.py`: authenticated structured API, using `h` readings.
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
or Tk text editing. Frozen executable packaging has not been verified; rebuild
with the updated spec and installed dependencies if distributing an EXE.

## Local verification

Verified on RTX 3060 Ti with PyTorch 2.8.0+cu128: CUDA inference, CPU inference,
both builder scan wrappers, saved-name exclusion and overlapping-window counts.
A repeated synthetic Chinese sample of 1,053,000 UTF-8 bytes took 18.86 seconds
after model loading; all expected occurrence counts matched. This is a speed
and stitching check, not a real-novel accuracy benchmark. No test files are
stored in the project.
