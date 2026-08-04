#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from abc import ABC, abstractmethod
from contextlib import nullcontext
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


BLOCK_SEPARATOR = "__SRT_BLOCK_SEP_f81d4fae7dec11d0a76500a0c91e6bf6__"
LINE_SEPARATOR = "__SRT_LINE_SEP_6bf6e91c0a00567a0d11ced7eaf4d18f__"


@dataclass
class SubtitleBlock:
    number: str
    timestamp: str
    text_lines: list[str]


class Translator(ABC):
    @abstractmethod
    def translate_batch(self, texts: list[str]) -> list[str]:
        raise NotImplementedError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate SRT subtitle text while preserving numbering and timestamps.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Subtitle files or directories to process. Directories are searched for *.English.srt by default.",
    )
    parser.add_argument(
        "--backend",
        choices=["google", "hf"],
        default="google",
        help="Translation backend. 'google' uses the public Google Translate endpoint, 'hf' uses a local Hugging Face model. Default: google",
    )
    parser.add_argument(
        "--source-lang",
        default="en",
        help="Source language code. Default: en",
    )
    parser.add_argument(
        "--target-lang",
        default="cs",
        help="Target language code. Default: cs",
    )
    parser.add_argument(
        "--model",
        default="Helsinki-NLP/opus-mt-en-cs",
        help="Model name or local path for the Hugging Face backend. Default: Helsinki-NLP/opus-mt-en-cs",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "mps"],
        default="auto",
        help="Execution device for the Hugging Face backend. Default: auto",
    )
    parser.add_argument(
        "--line-batch-size",
        type=int,
        default=32,
        help="Number of subtitle lines per local model batch. Default: 32",
    )
    parser.add_argument(
        "--pattern",
        default="*.English.srt",
        help="Glob used when a provided path is a directory. Default: *.English.srt",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output file.",
    )
    parser.add_argument(
        "--batch-chars",
        type=int,
        default=1800,
        help="Approximate character budget per translation request. Default: 1800",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.2,
        help="Pause between translation requests in seconds. Default: 0.2",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds. Default: 30",
    )
    return parser.parse_args()


def discover_files(raw_paths: list[str], pattern: str) -> list[Path]:
    files: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path).expanduser().resolve()
        if path.is_dir():
            files.extend(sorted(candidate for candidate in path.glob(pattern) if candidate.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"Path not found: {raw_path}")
    unique_files: list[Path] = []
    seen: set[Path] = set()
    for file_path in files:
        if file_path not in seen:
            seen.add(file_path)
            unique_files.append(file_path)
    return unique_files


def output_path_for(source_path: Path, target_lang: str) -> Path:
    if source_path.name.endswith(".English.srt"):
        return source_path.with_name(source_path.name[:-12] + f".{language_label(target_lang)}.srt")
    if source_path.suffix.lower() == ".srt":
        return source_path.with_name(source_path.stem + f".{target_lang}.srt")
    return source_path.with_name(source_path.name + f".{target_lang}.srt")


def language_label(language_code: str) -> str:
    labels = {
        "cs": "Czech",
    }
    return labels.get(language_code, language_code)


def parse_srt(content: str) -> list[SubtitleBlock]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks: list[SubtitleBlock] = []
    for raw_block in re.split(r"\n\s*\n", normalized):
        lines = raw_block.split("\n")
        if len(lines) < 2:
            continue
        blocks.append(
            SubtitleBlock(
                number=lines[0],
                timestamp=lines[1],
                text_lines=lines[2:],
            )
        )
    return blocks


def render_srt(blocks: list[SubtitleBlock]) -> str:
    parts = []
    for block in blocks:
        parts.append("\n".join([block.number, block.timestamp, *block.text_lines]))
    return "\n\n".join(parts) + "\n"


def request_translation(text: str, source_lang: str, target_lang: str, timeout: int) -> str:
    query = urllib.parse.quote(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={source_lang}&tl={target_lang}&dt=t&q={query}"
    )
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return "".join(part[0] for part in payload[0])


def request_with_retries(
    text: str,
    source_lang: str,
    target_lang: str,
    timeout: int,
    pause: float,
    retries: int = 5,
) -> str:
    delay = max(pause, 0.2)
    for attempt in range(retries + 1):
        try:
            return request_translation(text, source_lang, target_lang, timeout)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 503} or attempt == retries:
                raise
        except urllib.error.URLError:
            if attempt == retries:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("Translation failed after retries.")


class GoogleTranslator(Translator):
    def __init__(self, source_lang: str, target_lang: str, timeout: int, pause: float) -> None:
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.timeout = timeout
        self.pause = pause

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        payload = BLOCK_SEPARATOR.join(texts)
        translated = request_with_retries(
            payload,
            self.source_lang,
            self.target_lang,
            self.timeout,
            self.pause,
        )
        translated_blocks = translated.split(BLOCK_SEPARATOR)
        if len(translated_blocks) == len(texts):
            return translated_blocks
        return [
            request_with_retries(text, self.source_lang, self.target_lang, self.timeout, self.pause)
            for text in texts
        ]


class HuggingFaceTranslator(Translator):
    def __init__(
        self,
        source_lang: str,
        target_lang: str,
        model_name: str,
        device: str,
        line_batch_size: int,
    ) -> None:
        if source_lang != "en" or target_lang != "cs":
            raise ValueError(
                "The default Hugging Face setup currently expects an English-to-Czech model. "
                "Use a compatible model or extend the script for another language pair."
            )

        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as error:
            raise RuntimeError(
                "The Hugging Face backend requires 'transformers', 'torch', and usually 'sentencepiece'. "
                "Install them first, for example: pip install transformers torch sentencepiece"
            ) from error

        self._torch = torch
        self.line_batch_size = max(1, line_batch_size)
        self.device = self._resolve_device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        if self.device != "cpu":
            self.model.to(self.device)

    def _resolve_device(self, requested_device: str) -> str:
        if requested_device == "cpu":
            return "cpu"
        if requested_device == "mps":
            if self._torch.backends.mps.is_available():
                return "mps"
            raise RuntimeError("MPS was requested but is not available in the installed torch build.")
        if self._torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []

        translated: list[str] = []
        inference_context = self._torch.no_grad if self.device == "cpu" else self._torch.inference_mode

        with inference_context():
            for start in range(0, len(texts), self.line_batch_size):
                batch = texts[start : start + self.line_batch_size]
                encoded = self.tokenizer(batch, return_tensors="pt", padding=True, truncation=True)
                if self.device != "cpu":
                    encoded = {key: value.to(self.device) for key, value in encoded.items()}
                generated = self.model.generate(**encoded, max_new_tokens=256)
                translated.extend(self.tokenizer.batch_decode(generated, skip_special_tokens=True))

        return translated


def build_translator(args: argparse.Namespace) -> Translator:
    if args.backend == "google":
        return GoogleTranslator(
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            timeout=args.timeout,
            pause=args.pause,
        )
    return HuggingFaceTranslator(
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        model_name=args.model,
        device=args.device,
        line_batch_size=args.line_batch_size,
    )


def normalize_line(line: str) -> str:
    line = re.sub(r"\s+([,.!?])", r"\1", line)
    return line.strip()


def flush_batch(batch: list[SubtitleBlock], translator: Translator) -> list[SubtitleBlock]:
    payloads = [LINE_SEPARATOR.join(block.text_lines) for block in batch]
    translated_payloads = translator.translate_batch(payloads)

    if len(translated_payloads) != len(batch):
        raise RuntimeError("Translated batch size mismatch.")

    output: list[SubtitleBlock] = []
    for block, translated_text in zip(batch, translated_payloads):
        text_lines = [normalize_line(line) for line in translated_text.split(LINE_SEPARATOR)]
        output.append(
            SubtitleBlock(
                number=block.number,
                timestamp=block.timestamp,
                text_lines=text_lines,
            )
        )
    return output


def translate_blocks(
    blocks: list[SubtitleBlock],
    translator: Translator,
    pause: float,
    batch_chars: int,
) -> list[SubtitleBlock]:
    translated: list[SubtitleBlock] = []
    batch: list[SubtitleBlock] = []
    batch_size = 0

    for index, block in enumerate(blocks, start=1):
        payload_piece = LINE_SEPARATOR.join(block.text_lines)
        projected_size = batch_size + len(payload_piece) + len(BLOCK_SEPARATOR) + 8
        if batch and projected_size > batch_chars:
            translated.extend(flush_batch(batch, translator))
            batch = []
            batch_size = 0
            if pause > 0:
                time.sleep(pause)

        batch.append(block)
        batch_size += len(payload_piece) + len(BLOCK_SEPARATOR) + 8

        if index % 100 == 0:
            print(f"Processed {index}/{len(blocks)} subtitle blocks...", file=sys.stderr)

    if batch:
        translated.extend(flush_batch(batch, translator))

    return translated


def process_file(
    file_path: Path,
    target_lang: str,
    translator: Translator,
    pause: float,
    batch_chars: int,
    overwrite: bool,
) -> Path:
    destination = output_path_for(file_path, target_lang)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {destination}")

    content = file_path.read_text(encoding="utf-8")
    blocks = parse_srt(content)
    translated_blocks = translate_blocks(
        blocks,
        translator=translator,
        pause=pause,
        batch_chars=batch_chars,
    )
    destination.write_text(render_srt(translated_blocks), encoding="utf-8")
    return destination


def main() -> int:
    args = parse_args()
    try:
        files = discover_files(args.paths, args.pattern)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not files:
        print("No subtitle files found.", file=sys.stderr)
        return 1

    try:
        translator = build_translator(args)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    failures = 0
    for file_path in files:
        print(f"Translating {file_path}...", file=sys.stderr)
        try:
            destination = process_file(
                file_path=file_path,
                target_lang=args.target_lang,
                translator=translator,
                pause=args.pause,
                batch_chars=args.batch_chars,
                overwrite=args.overwrite,
            )
        except Exception as error:
            failures += 1
            print(f"Failed: {file_path}: {error}", file=sys.stderr)
            continue
        print(f"Wrote {destination}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
