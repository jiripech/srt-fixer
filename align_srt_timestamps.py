#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubtitleBlock:
    number: str
    timestamp: str
    text_lines: list[str]


@dataclass
class AlignmentGroup:
    src_start: int
    src_end: int
    dst_start: int
    dst_end: int
    src_span_units: int
    dst_span_units: int
    expected_dst_units: float
    size_cost: float
    shape_cost: float
    total_cost: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Align translated subtitles to timestamps from an original SRT file. "
            "The output uses numbering and timestamps from the original file."
        )
    )
    parser.add_argument("original", help="Original SRT with correct timestamps")
    parser.add_argument("translated", help="Translated SRT with potentially wrong timestamps")
    parser.add_argument("output", nargs="?", help="Output SRT path")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output file if it already exists.",
    )
    parser.add_argument(
        "--max-group",
        type=int,
        default=3,
        help="Maximum consecutive blocks grouped during alignment. Default: 3",
    )
    parser.add_argument(
        "--group-penalty",
        type=float,
        default=0.25,
        help="Penalty for split/merge complexity during alignment. Default: 0.25",
    )
    parser.add_argument(
        "--renumber",
        action="store_true",
        help="Rewrite subtitle numbers to a clean 1..N sequence.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze alignment only and print suspicious segments without writing output.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero exit code when suspicious segments are detected.",
    )
    parser.add_argument(
        "--ignore-sdh",
        action="store_true",
        help="Keep original SDH cue lines (in (...) or [...]) instead of translated text.",
    )
    return parser.parse_args()


def parse_srt(content: str) -> list[SubtitleBlock]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    blocks: list[SubtitleBlock] = []
    for raw_block in re.split(r"\n\s*\n", normalized):
        lines = [line for line in raw_block.split("\n")]
        if len(lines) < 2:
            continue
        blocks.append(
            SubtitleBlock(
                number=lines[0].strip(),
                timestamp=lines[1].strip(),
                text_lines=[line.rstrip() for line in lines[2:]] if len(lines) > 2 else [""],
            )
        )
    return blocks


def render_srt(blocks: list[SubtitleBlock]) -> str:
    parts: list[str] = []
    for block in blocks:
        text_lines = block.text_lines if block.text_lines else [""]
        parts.append("\n".join([block.number, block.timestamp, *text_lines]))
    return "\n\n".join(parts) + "\n"


def normalize_for_length(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u200b", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_sdh_line(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    return bool(re.fullmatch(r"[\[(].*[\])]", normalized))


def is_sdh_only_block(block: SubtitleBlock) -> bool:
    non_empty = [line.strip() for line in block.text_lines if line.strip()]
    if not non_empty:
        return False
    return all(is_sdh_line(line) for line in non_empty)


def sdh_line_ratio(blocks: list[SubtitleBlock]) -> float:
    total_lines = 0
    sdh_lines = 0
    for block in blocks:
        for line in block.text_lines:
            normalized = line.strip()
            if not normalized:
                continue
            total_lines += 1
            if is_sdh_line(normalized):
                sdh_lines += 1
    if total_lines == 0:
        return 0.0
    return sdh_lines / total_lines


def block_plain_text(block: SubtitleBlock) -> str:
    return " ".join(line.strip() for line in block.text_lines if line is not None).strip()


def length_units(text: str) -> int:
    normalized = normalize_for_length(text)
    if not normalized:
        return 1
    return max(1, len(normalized))


def choose_split_index(text: str, target: int, left_bound: int, right_bound: int) -> int:
    if left_bound >= right_bound:
        return max(1, min(len(text) - 1, target))

    punctuation_positions = [
        idx
        for idx, ch in enumerate(text)
        if ch in ".!?;,:" and left_bound <= idx + 1 <= right_bound
    ]
    if punctuation_positions:
        return min(punctuation_positions, key=lambda p: abs((p + 1) - target)) + 1

    spaces = [idx for idx, ch in enumerate(text) if ch == " " and left_bound <= idx + 1 <= right_bound]
    if spaces:
        return min(spaces, key=lambda p: abs((p + 1) - target)) + 1

    return max(left_bound, min(right_bound, target))


def split_text_by_weights(text: str, weights: list[int]) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    count = len(weights)
    if count == 0:
        return []
    if count == 1:
        return [cleaned]
    if not cleaned:
        return [""] * count

    chars = len(cleaned)
    total_weight = max(1, sum(max(1, weight) for weight in weights))

    remaining = cleaned
    remaining_weight = total_weight
    parts: list[str] = []

    for idx in range(count - 1):
        weight = max(1, weights[idx])
        ideal_cut = int(round(len(remaining) * (weight / max(1, remaining_weight))))
        min_cut = max(1, int(len(remaining) * 0.2))
        max_cut = min(len(remaining) - (count - idx - 1), int(len(remaining) * 0.8))
        if min_cut > max_cut:
            min_cut = 1
            max_cut = len(remaining) - (count - idx - 1)

        split_at = choose_split_index(remaining, ideal_cut, min_cut, max_cut)
        left = remaining[:split_at].strip()
        remaining = remaining[split_at:].strip()
        parts.append(left)
        remaining_weight -= weight

    parts.append(remaining.strip())

    if len(parts) < count:
        parts.extend([""] * (count - len(parts)))

    if len(parts) > count:
        parts = parts[: count - 1] + [" ".join(parts[count - 1 :]).strip()]

    return parts


def split_text_to_line_template(text: str, template_lines: list[str]) -> list[str]:
    line_count = max(1, len(template_lines))
    if line_count == 1:
        return [re.sub(r"\s+", " ", text).strip()]

    weights = [max(1, len(normalize_for_length(line))) for line in template_lines]
    return split_text_by_weights(text, weights)


def align_groups(
    original_blocks: list[SubtitleBlock],
    translated_blocks: list[SubtitleBlock],
    max_group: int,
    group_penalty: float,
) -> list[AlignmentGroup]:
    n = len(original_blocks)
    m = len(translated_blocks)

    src_units = [length_units(block_plain_text(block)) for block in original_blocks]
    dst_units = [length_units(block_plain_text(block)) for block in translated_blocks]

    total_src = max(1, sum(src_units))
    total_dst = max(1, sum(dst_units))
    ratio = total_dst / total_src

    inf = float("inf")
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    prev: list[list[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    src_prefix = [0]
    dst_prefix = [0]
    for value in src_units:
        src_prefix.append(src_prefix[-1] + value)
    for value in dst_units:
        dst_prefix.append(dst_prefix[-1] + value)

    def range_sum(prefix: list[int], start: int, end: int) -> int:
        return prefix[end] - prefix[start]

    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == inf:
                continue

            for src_take in range(1, max_group + 1):
                ni = i + src_take
                if ni > n:
                    break
                for dst_take in range(1, max_group + 1):
                    nj = j + dst_take
                    if nj > m:
                        break

                    src_span = range_sum(src_prefix, i, ni)
                    dst_span = range_sum(dst_prefix, j, nj)

                    expected_dst = max(1.0, src_span * ratio)
                    size_cost = abs(dst_span - expected_dst) / expected_dst
                    shape_cost = group_penalty * abs(src_take - dst_take)
                    cost = size_cost + shape_cost

                    candidate = dp[i][j] + cost
                    if candidate < dp[ni][nj]:
                        dp[ni][nj] = candidate
                        prev[ni][nj] = (i, j)

    if prev[n][m] is None and not (n == 0 and m == 0):
        raise RuntimeError(
            "Could not align subtitle files. Try increasing --max-group or verify both files contain the same dialogue order."
        )

    path: list[tuple[int, int, int, int]] = []
    ci, cj = n, m
    while ci > 0 or cj > 0:
        parent = prev[ci][cj]
        if parent is None:
            raise RuntimeError("Alignment traceback failed.")
        pi, pj = parent
        path.append((pi, ci, pj, cj))
        ci, cj = pi, pj

    path.reverse()

    groups: list[AlignmentGroup] = []
    for src_start, src_end, dst_start, dst_end in path:
        src_span = range_sum(src_prefix, src_start, src_end)
        dst_span = range_sum(dst_prefix, dst_start, dst_end)
        expected_dst = max(1.0, src_span * ratio)
        size_cost = abs(dst_span - expected_dst) / expected_dst
        shape_cost = group_penalty * abs((src_end - src_start) - (dst_end - dst_start))
        groups.append(
            AlignmentGroup(
                src_start=src_start,
                src_end=src_end,
                dst_start=dst_start,
                dst_end=dst_end,
                src_span_units=src_span,
                dst_span_units=dst_span,
                expected_dst_units=expected_dst,
                size_cost=size_cost,
                shape_cost=shape_cost,
                total_cost=size_cost + shape_cost,
            )
        )

    return groups


def first_non_empty_line(block: SubtitleBlock) -> str:
    for line in block.text_lines:
        normalized = re.sub(r"\s+", " ", line).strip()
        if normalized:
            return normalized
    return ""


def last_non_empty_line(block: SubtitleBlock) -> str:
    for line in reversed(block.text_lines):
        normalized = re.sub(r"\s+", " ", line).strip()
        if normalized:
            return normalized
    return ""


def timestamp_range(block: SubtitleBlock) -> tuple[str, str]:
    parts = [part.strip() for part in block.timestamp.split("-->", maxsplit=1)]
    if len(parts) != 2:
        return "00:00:00", "00:00:00"
    start = parts[0].split(",", maxsplit=1)[0]
    end = parts[1].split(",", maxsplit=1)[0]
    return start, end


def find_suspicious_segments(
    original_blocks: list[SubtitleBlock],
    translated_blocks: list[SubtitleBlock],
    groups: list[AlignmentGroup],
) -> list[tuple[int, int, list[str]]]:
    suspicious_groups: list[tuple[int, AlignmentGroup, list[str]]] = []

    for index, group in enumerate(groups):
        src_count = group.src_end - group.src_start
        dst_count = group.dst_end - group.dst_start
        dst_text = " ".join(
            block_plain_text(block) for block in translated_blocks[group.dst_start : group.dst_end]
        ).strip()

        reasons: list[str] = []
        if src_count != dst_count:
            reasons.append("split/merge mismatch")
        if group.size_cost >= 0.6:
            reasons.append("length ratio drift")
        if not dst_text:
            reasons.append("possible missing translation")
        elif group.expected_dst_units > 0 and group.dst_span_units / group.expected_dst_units < 0.45:
            reasons.append("possible missing translation")

        if reasons:
            suspicious_groups.append((index, group, reasons))

    if not suspicious_groups:
        return []

    merged: list[tuple[int, int, list[str]]] = []
    for _, group, reasons in suspicious_groups:
        if not merged:
            merged.append((group.src_start, group.src_end, reasons.copy()))
            continue

        prev_start, prev_end, prev_reasons = merged[-1]
        if prev_end == group.src_start:
            reason_set = sorted(set(prev_reasons + reasons))
            merged[-1] = (prev_start, group.src_end, reason_set)
        else:
            merged.append((group.src_start, group.src_end, reasons.copy()))

    return merged


def print_dry_run_report(
    original_blocks: list[SubtitleBlock],
    translated_blocks: list[SubtitleBlock],
    groups: list[AlignmentGroup],
) -> int:
    segments = find_suspicious_segments(original_blocks, translated_blocks, groups)
    if not segments:
        print("No suspicious segments detected.")
        return 0

    for src_start, src_end, reasons in segments:
        first_block = original_blocks[src_start]
        last_block = original_blocks[src_end - 1]
        start_ts, _ = timestamp_range(first_block)
        _, end_ts = timestamp_range(last_block)
        first_line = first_non_empty_line(first_block) or "<empty>"
        last_line = last_non_empty_line(last_block) or "<empty>"
        segment_lines = max(1, src_end - src_start)

        print(
            f"Sus segment of {segment_lines} lines starts at {start_ts} with line: {first_line} "
            f"and ends at {end_ts} with line: {last_line}"
        )
        print(f"Reason: {', '.join(reasons)}")

    return len(segments)


def assign_translated_text(
    original_group: list[SubtitleBlock],
    translated_group: list[SubtitleBlock],
    ignore_sdh: bool,
) -> list[list[str]]:
    src_count = len(original_group)
    dst_count = len(translated_group)

    dst_texts = [block_plain_text(block) for block in translated_group]

    if src_count == dst_count:
        paired: list[list[str]] = []
        for source_block, translated_text in zip(original_group, dst_texts):
            paired.append(split_text_to_line_template(translated_text, source_block.text_lines))
        return paired

    merged_text = " ".join(text for text in dst_texts if text).strip()
    src_weights = [length_units(block_plain_text(block)) for block in original_group]
    split_for_blocks = split_text_by_weights(merged_text, src_weights)

    assigned: list[list[str]] = []
    for source_block, block_text in zip(original_group, split_for_blocks):
        assigned.append(split_text_to_line_template(block_text, source_block.text_lines))

    return assigned


def build_output_blocks(
    original_blocks: list[SubtitleBlock],
    translated_blocks: list[SubtitleBlock],
    groups: list[AlignmentGroup],
    renumber: bool,
    ignore_sdh: bool,
) -> list[SubtitleBlock]:
    output: list[SubtitleBlock] = []

    for group in groups:
        src_group = original_blocks[group.src_start : group.src_end]
        dst_group = translated_blocks[group.dst_start : group.dst_end]
        assigned_text = assign_translated_text(src_group, dst_group, ignore_sdh=ignore_sdh)

        for index, source_block in enumerate(src_group):
            number = str(len(output) + 1) if renumber else source_block.number
            lines = assigned_text[index] if index < len(assigned_text) else [""]
            if ignore_sdh:
                preserved: list[str] = []
                source_lines = source_block.text_lines if source_block.text_lines else [""]
                for line_index, line in enumerate(lines):
                    source_line = source_lines[line_index] if line_index < len(source_lines) else ""
                    if is_sdh_line(source_line):
                        preserved.append(source_line.strip())
                    else:
                        preserved.append(line)
                lines = preserved
            cleaned_lines = [re.sub(r"\s+", " ", line).strip() for line in lines]
            if not any(cleaned_lines):
                cleaned_lines = [""]
            output.append(
                SubtitleBlock(
                    number=number,
                    timestamp=source_block.timestamp,
                    text_lines=cleaned_lines,
                )
            )

    return output


def build_output_blocks_ignore_sdh(
    original_blocks: list[SubtitleBlock],
    translated_blocks: list[SubtitleBlock],
    max_group: int,
    group_penalty: float,
    renumber: bool,
) -> tuple[list[SubtitleBlock], list[SubtitleBlock], list[AlignmentGroup]]:
    active_original_blocks = [block for block in original_blocks if not is_sdh_only_block(block)]
    if not active_original_blocks:
        output: list[SubtitleBlock] = []
        for index, block in enumerate(original_blocks):
            number = str(index + 1) if renumber else block.number
            output.append(
                SubtitleBlock(
                    number=number,
                    timestamp=block.timestamp,
                    text_lines=[line.strip() for line in block.text_lines] if block.text_lines else [""],
                )
            )
        return output, active_original_blocks, []

    active_groups = align_groups(
        original_blocks=active_original_blocks,
        translated_blocks=translated_blocks,
        max_group=max_group,
        group_penalty=group_penalty,
    )
    active_output = build_output_blocks(
        original_blocks=active_original_blocks,
        translated_blocks=translated_blocks,
        groups=active_groups,
        renumber=False,
        ignore_sdh=True,
    )

    merged_output: list[SubtitleBlock] = []
    spoken_index = 0
    for original_index, original_block in enumerate(original_blocks):
        if is_sdh_only_block(original_block):
            number = str(len(merged_output) + 1) if renumber else original_block.number
            merged_output.append(
                SubtitleBlock(
                    number=number,
                    timestamp=original_block.timestamp,
                    text_lines=[line.strip() for line in original_block.text_lines] if original_block.text_lines else [""],
                )
            )
            continue

        if spoken_index >= len(active_output):
            spoken_lines = [""]
        else:
            spoken_lines = active_output[spoken_index].text_lines
        spoken_index += 1

        number = str(len(merged_output) + 1) if renumber else original_block.number
        merged_output.append(
            SubtitleBlock(
                number=number,
                timestamp=original_block.timestamp,
                text_lines=spoken_lines if spoken_lines else [""],
            )
        )

    return merged_output, active_original_blocks, active_groups


def read_srt(path: Path) -> list[SubtitleBlock]:
    return parse_srt(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    original_path = Path(args.original).expanduser().resolve()
    translated_path = Path(args.translated).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else None

    if not original_path.is_file():
        print(f"Error: original file not found: {original_path}", file=sys.stderr)
        return 1
    if not translated_path.is_file():
        print(f"Error: translated file not found: {translated_path}", file=sys.stderr)
        return 1
    if args.max_group < 1:
        print("Error: --max-group must be >= 1", file=sys.stderr)
        return 1
    if not args.dry_run and output_path is None:
        print("Error: output path is required unless --dry-run is used.", file=sys.stderr)
        return 1
    if output_path is not None and output_path.exists() and not args.overwrite and not args.dry_run:
        print(f"Error: output already exists: {output_path}. Use --overwrite.", file=sys.stderr)
        return 1

    try:
        original_blocks = read_srt(original_path)
        translated_blocks = read_srt(translated_path)
        if not original_blocks:
            raise RuntimeError("Original SRT is empty or invalid.")
        if not translated_blocks:
            raise RuntimeError("Translated SRT is empty or invalid.")

        original_sdh_ratio = sdh_line_ratio(original_blocks)
        translated_sdh_ratio = sdh_line_ratio(translated_blocks)
        if not args.ignore_sdh and original_sdh_ratio >= 0.08 and translated_sdh_ratio <= 0.03:
            print(
                "Note: original subtitles appear to contain many SDH cue lines while translation does not. "
                "Consider rerunning with --ignore-sdh.",
                file=sys.stderr,
            )

        groups = align_groups(
            original_blocks=original_blocks,
            translated_blocks=translated_blocks,
            max_group=args.max_group,
            group_penalty=max(0.0, args.group_penalty),
        )

        report_original_blocks = original_blocks
        output_blocks: list[SubtitleBlock] | None = None
        if args.ignore_sdh:
            output_blocks, report_original_blocks, groups = build_output_blocks_ignore_sdh(
                original_blocks=original_blocks,
                translated_blocks=translated_blocks,
                max_group=args.max_group,
                group_penalty=max(0.0, args.group_penalty),
                renumber=args.renumber,
            )

        suspicious_count = 0
        if args.dry_run or args.strict:
            suspicious_count = print_dry_run_report(report_original_blocks, translated_blocks, groups)

        if args.strict and suspicious_count > 0:
            print(
                f"Strict mode: detected {suspicious_count} suspicious segment(s).",
                file=sys.stderr,
            )
            return 2

        if args.dry_run:
            return 0

        if output_blocks is None:
            output_blocks = build_output_blocks(
                original_blocks=original_blocks,
                translated_blocks=translated_blocks,
                groups=groups,
                renumber=args.renumber,
                ignore_sdh=args.ignore_sdh,
            )
        if output_path is None:
            raise RuntimeError("Output path resolution failed.")
        output_path.write_text(render_srt(output_blocks), encoding="utf-8")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Wrote aligned subtitles: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
