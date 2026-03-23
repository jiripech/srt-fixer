# SRT Fixer App

A simple Progressive Web App for fixing translated SRT files with:

- visual editor
- local correction history in `localStorage`
- voice dictation (SpeechRecognition)
- export of final SRT
- offline support via service worker

## Usage

1. Open `index.html` in a browser.
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

- import/export JSON correction history
- add tests
- add multi-language support
- improve exact timing and blank line handling

## How to run

1. Open the `srt-fix-pwa` directory.
2. In a browser, load `index.html`.
3. Upload your source translation (`*.srt`).
4. Edit text lines; all changes are stored to local history.
5. Click `Apply Corrections` to reload from history, then `Export SRT`.
6. `Save Corrections` in localStorage keeps changes after reload.
