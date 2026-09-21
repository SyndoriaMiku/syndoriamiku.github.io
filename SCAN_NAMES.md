# Scan Names

Both builders use `name_scanner.py` for discovery and `name_suggestions.py`
for API suggestions. Install `requirements-scanner.txt` in the Python
environment that runs the builder (`jieba==0.42.1`).

## Recognition

The scanner checks Chinese dictionary words and word classes with jieba,
then requires name evidence: an introduction, a speaking/acting subject,
an honorific, or a direct address. Entity discovery uses explicit contexts
for organizations, places, skills and items. The scanner does not infer that
a Chinese word is a name from its Vietnamese translation.

Saved glossary entries are masked before discovery. Counts represent actual
non-overlapping occurrences after discovery. Repetition does not raise the
ranking score. Scores are rule weights, not calibrated probabilities.
Repeated runs and candidate word segmentation are cached within bounded
memory. Very unusual names, aliases and foreign transliterations may be
missed; manual name entry remains available.

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

## Reference and verification

Reference: https://moxhi.pages.dev/ . Its deployed scanner uses the `r6b TP`
WebGPU model. This Python implementation does **not** embed or reproduce that
model: it uses a lexicon and contextual rules. The reference informed the
separation between discovery, readings and manual glossary review.

Local checks cover reported false positives, personal/organization/place/
skill/item examples, counts, existing glossary exclusion, API response
alignment, caching and both Tk review dialogs. The 1.44 MB speed sample is
synthetic; it is not a real-novel accuracy benchmark.
