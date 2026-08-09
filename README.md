# SRT Fixer App

A simple Progressive Web App for fixing translated SRT files with:

- visual editor
- local correction history in `localStorage`
- voice dictation (SpeechRecognition)
- export of final SRT
- offline support via service worker

## Usage

1. Open [SRT Fixer](https://srtfx.hq.cz "SRT Fixer App") in a browser.
2. Load a `*.srt` file.
3. Edit the text; changes are saved automatically to history.
4. Click `Apply Corrections` or `Save Corrections`.
5. Export with `Export SRT`.

## What is implemented

- load SRT file and parse blocks (id + timecode + text)
- render each block in an editable textarea
- mark modified blocks (green highlight)
- save corrections to `localStorage` (history by block id)
- apply saved history back into the editor
- export modified SRT as downloadable `patched.srt`
- speech dictation using `SpeechRecognition` (Chrome/Edge)
- PWA manifest + service worker for offline usage

## Plan for 2026

- [import/export JSON correction history](
  https://github.com/jiripech/srt-fixer/issues/1 "Github Issue #1"
)
- [add tests](https://github.com/jiripech/srt-fixer/pull/2 "Github Copilot Pull request #2")
- [add multi-language support](https://github.com/jiripech/srt-fixer/issues/2 "Github Issue #3")

## How to run

1. Clone this repository to your local storage
  [in way you prefer](
  https://docs.github.com/en/get-started/git-basics/about-remote-repositories#cloning-with-ssh-urls
  "Github Docs: Cloning with SSH URLs").
2. In a browser, open `index.html`.
3. Upload your source translation (`*.srt`).
4. Edit text lines; all changes are stored to local history.
5. Click `Apply Corrections` to reload from history, then `Export SRT`.
6. `Save Corrections` in localStorage keeps changes after reload.

## Timestamp alignment script

Use `align_srt_timestamps.py` when you have:

- an original SRT with correct timestamps
- a translated SRT with incorrect timestamps

The script keeps timestamps from the original file and maps translated text
onto them,
including basic split/merge handling between neighboring subtitle blocks.

Example:

```bash
python3 align_srt_timestamps.py original.srt translated.srt output.srt
```

Dry-run consistency check (no output file is written):

```bash
python3 align_srt_timestamps.py original.srt translated.srt --dry-run
```

Useful options:

- `--overwrite` overwrite existing output file
- `--max-group 4` allow larger split/merge groups
- `--group-penalty 0.25` tune how strongly split/merge mismatch is penalized
  during alignment
- `--renumber` rewrite subtitle numbering to `1..N`
- `--dry-run` print suspicious segments (possible shifts or missing
  translation parts)
- `--strict` return non-zero exit code if suspicious segments are detected
- `--ignore-sdh` keep original SDH cue lines (`(...)` or `[...]`) in the output

When the original seems SDH-heavy and translation is not, the script prints a
hint to rerun with `--ignore-sdh`.

### Alignment checks and safeguards

The aligner contains several built-in checks to reduce common subtitle retiming
failures.

#### 1. Monotonic group alignment

- Source and translated blocks are aligned in order only (no reordering).
- Dynamic programming builds local groups (default up to 3 blocks) and
  minimizes:
  - text-length ratio drift
  - split/merge shape mismatch

#### 2. Suspicious segment detection (`--dry-run` / `--strict`)

- A segment is flagged when one or more checks match:
  - split/merge mismatch (`src_count != dst_count`)
  - large length drift (`size_cost >= 0.6`)
  - missing or near-missing translated text
- `--dry-run` prints a readable report with time span and first/last line.
- `--strict` exits with code `2` when suspicious segments are found.

#### 3. SDH-aware behavior (`--ignore-sdh`)

- SDH-only source blocks are excluded from spoken-text alignment and then
  reinserted unchanged.
- In mixed blocks (spoken + SDH line), SDH lines are preserved and spoken text
  is mapped only to spoken lines.
- This avoids SDH cues stealing spoken text and causing downstream drift.

#### 4. Split quality checks

- Token-boundary splitting is used to avoid breaking words into letters.
- Single-token text is never force-split across multiple lines.
- Empty lines are cleaned to avoid accidental triple-newline output.

#### 5. Over-stretch safeguards

- When one translated block must fill multiple source blocks, constrained
  partitioning limits how many source blocks one translated chunk can span.
- If constraints are impossible for a local group, the script falls back to
  unconstrained partitioning instead of failing.
- A local boundary refinement pass adjusts neighboring groups around
  question-mark boundaries to reduce visible sentence leakage.

### Regression tests

Regression tests live in `tests/test_align_srt_timestamps.py` and cover:

- single-token no-letter-split behavior
- mixed spoken+SDH line preservation
- no extra blank lines in rendered SRT
- anti-stretch announcement scenario

Run tests:

```bash
python3 -m unittest tests/test_align_srt_timestamps.py
```

Playwright note:

- E2E tests are run via `npm run test:e2e`.
- `@playwright/test` is pinned to `1.61.0` in this repository because an older
  version caused local test execution issues.

### Recommended workflow for production files

#### 1. Run a safety pass first

```bash
python3 align_srt_timestamps.py original.srt translated.srt --dry-run
```

#### 2. If SDH mismatch is likely, run with SDH protection

```bash
python3 align_srt_timestamps.py original.srt translated.srt output.srt \
  --ignore-sdh --renumber
```

#### 3. For CI or strict QA, enforce failure on suspicious segments

```bash
python3 align_srt_timestamps.py original.srt translated.srt --dry-run --strict
```
