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

- [import/export JSON correction history](https://github.com/jiripech/srt-fixer/issues/1 "Github Issue #1")
- [add tests](https://github.com/jiripech/srt-fixer/pull/2 "Github Copilot Pull request #2")
- [add multi-language support](https://github.com/jiripech/srt-fixer/issues/2 "Github Issue #3")

## How to run

1. Clone this repository to your local storage [in way you prefer](https://docs.github.com/en/get-started/git-basics/about-remote-repositories#cloning-with-ssh-urls "Github Docs: Cloning with SSH URLs").
2. In a browser, open `index.html`.
3. Upload your source translation (`*.srt`).
4. Edit text lines; all changes are stored to local history.
5. Click `Apply Corrections` to reload from history, then `Export SRT`.
6. `Save Corrections` in localStorage keeps changes after reload.
