import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import align_srt_timestamps as align


class AlignSrtTimestampTests(unittest.TestCase):
    def _block(self, number: str, timestamp: str, *lines: str) -> align.SubtitleBlock:
        return align.SubtitleBlock(number=number, timestamp=timestamp, text_lines=list(lines) if lines else [""])

    def test_single_token_is_not_split_into_letters(self) -> None:
        parts = align.split_text_to_line_template("Promin.", ["line1", "line2"])
        self.assertEqual(parts[0], "Promin.")
        self.assertEqual(parts[1], "")

    def test_mixed_sdh_line_keeps_full_spoken_text(self) -> None:
        original = [
            self._block("1", "00:00:01,000 --> 00:00:03,000", "I spoke to a guy in the village.", "(clanking)"),
            self._block("2", "00:00:03,000 --> 00:00:05,000", "He will find me work."),
        ]
        translated = [
            self._block("1", "00:00:01,000 --> 00:00:03,000", "Mluvila jsem s clovekem z nasi vesnice."),
            self._block("2", "00:00:03,000 --> 00:00:05,000", "Najde mi praci."),
        ]

        output, _, _ = align.build_output_blocks_ignore_sdh(
            original_blocks=original,
            translated_blocks=translated,
            max_group=3,
            group_penalty=0.25,
            renumber=True,
        )

        self.assertEqual(output[0].text_lines[0], "Mluvila jsem s clovekem z nasi vesnice.")
        self.assertIn("(clanking)", output[0].text_lines)

    def test_no_extra_blank_lines_in_rendered_output(self) -> None:
        blocks = [
            self._block("1", "00:00:01,000 --> 00:00:02,000", "Promin."),
            self._block("2", "00:00:02,500 --> 00:00:03,000", "(sound)"),
        ]
        rendered = align.render_srt(blocks)
        self.assertNotIn("\n\n\n", rendered)

    def test_announcement_chunk_not_stretched_across_too_many_blocks(self) -> None:
        original = [
            self._block("1", "00:57:15,833 --> 00:57:19,083", "Sorry baby."),
            self._block("2", "00:57:32,246 --> 00:57:36,938", "(emotional music)"),
            self._block("3", "00:57:49,375 --> 00:57:54,875", "Attention all passengers,"),
            self._block("4", "00:57:55,042 --> 00:57:57,292", "due to water logging,"),
            self._block("5", "00:57:57,458 --> 00:57:59,500", "all trains are delayed."),
            self._block("6", "00:57:59,667 --> 00:58:03,750", "Stand by for further updates."),
            self._block("7", "00:58:06,708 --> 00:58:07,833", "Hello?"),
        ]
        translated = [
            self._block("1", "00:57:07,292 --> 00:57:11,124", "Je mi to lito, lasko."),
            self._block("2", "00:57:40,916 --> 00:57:46,559", "Upozorneni pro vsechny cestujici:"),
            self._block("3", "00:57:46,583 --> 00:57:51,184", "z duvodu odcerpavani vody", "maji vsechny vlaky zpozdeni."),
            self._block("4", "00:57:51,208 --> 00:57:55,792", "Vyckejte na dalsi pokyny."),
            self._block("5", "00:57:58,250 --> 00:57:59,958", "Halo?"),
        ]

        output, _, _ = align.build_output_blocks_ignore_sdh(
            original_blocks=original,
            translated_blocks=translated,
            max_group=3,
            group_penalty=0.25,
            renumber=True,
        )

        # The "Sorry baby" translation stays whole and does not leak into the announcement.
        self.assertEqual(output[0].text_lines[0], "Je mi to lito, lasko.")

        # The announcement should be contained in at most 3 spoken blocks, not stretched over 5.
        spoken_lines = [" ".join(block.text_lines) for block in output]
        start = next(i for i, text in enumerate(spoken_lines) if "Upozorneni" in text)
        end = next(i for i, text in enumerate(spoken_lines) if "zpozdeni." in text)
        self.assertLessEqual(end - start, 2)

        # Follow-up instruction should remain after the delay sentence, not mixed into it.
        updates_index = next(i for i, text in enumerate(spoken_lines) if "Vyckejte" in text)
        self.assertGreater(updates_index, end)

        # Sentence integrity takes precedence over filling every timestamp block.
        self.assertIn("Halo?", spoken_lines)

    def test_short_vocative_question_is_not_split(self) -> None:
        original = [
            self._block("1", "00:00:01,000 --> 00:00:02,000", "Hello?"),
            self._block("2", "00:00:02,000 --> 00:00:03,000", "Hello, Mama?"),
            self._block("3", "00:00:03,000 --> 00:00:04,000", "How are you feeling?"),
            self._block("4", "00:00:04,000 --> 00:00:05,000", "No, nothing's wrong."),
            self._block("5", "00:00:05,000 --> 00:00:06,000", "I'm just calling."),
        ]
        translated = [
            self._block("1", "00:00:01,000 --> 00:00:02,000", "Halo?"),
            self._block("2", "00:00:02,000 --> 00:00:03,000", "Halo, mami?"),
            self._block("3", "00:00:03,000 --> 00:00:04,000", "Jak se mas?"),
            self._block("4", "00:00:04,000 --> 00:00:05,000", "Ne, nic se nedeje."),
        ]

        output, _, _ = align.build_output_blocks_ignore_sdh(
            original_blocks=original,
            translated_blocks=translated,
            max_group=3,
            group_penalty=0.25,
            renumber=True,
        )

        spoken_lines = [" ".join(block.text_lines).strip() for block in output]
        self.assertIn("Halo, mami?", spoken_lines)
        self.assertNotIn("Halo,", spoken_lines)
        self.assertNotIn("mami?", spoken_lines)
        self.assertIn("Ne, nic se nedeje.", spoken_lines)


if __name__ == "__main__":
    unittest.main()
