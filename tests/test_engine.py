"""Engine tests on rendered text, so the expected answer is known exactly."""

import os
import sys
import unittest

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pluck import engine  # noqa: E402

SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def render(lines, font=SANS, size=14, dark=True):
    f = ImageFont.truetype(font, size)
    width = max(int(f.getlength(l)) for l in lines) + 40
    height = len(lines) * size * 2 + 20
    im = Image.new("RGB", (width, height), (24, 24, 28) if dark else (250, 250, 250))
    d = ImageDraw.Draw(im)
    for i, line in enumerate(lines):
        d.text((20, 10 + i * size * 2), line, font=f, fill=(225, 225, 230) if dark else (30, 30, 30))
    return im


class EngineTest(unittest.TestCase):
    def test_reads_a_terminal_command(self):
        cmd = "sudo apt install --no-install-recommends ffmpeg"
        result = engine.recognize(render([cmd], MONO, 13), "eng")
        self.assertEqual(result.text, cmd)

    def test_keeps_lines_apart_and_in_order(self):
        lines = ["First line of text here", "Second line follows it", "And a third one"]
        result = engine.recognize(render(lines, dark=False), "eng")
        self.assertEqual(result.text.splitlines(), lines)

    def test_word_boxes_map_back_to_the_original_pixels(self):
        im = render(["Hello world"], size=16)
        result = engine.recognize(im, "eng")
        word = result.lines[0].words[0]
        self.assertEqual(word.text, "Hello")
        # drawn at x=20; the box must be near there, not at the 2x position
        self.assertLess(abs(word.x - 20), 4)
        self.assertLess(word.x + word.w, im.width)

    def test_real_terminal_capture(self):
        """A real screenshot of monospace text: a lowercase l with a curved
        foot (read as L) and a link Tesseract splits in two."""
        here = os.path.dirname(os.path.abspath(__file__))
        result = engine.recognize(Image.open(os.path.join(here, "fixtures", "terminal-mono.png")))
        self.assertEqual(result.text,
                         "sudo apt install --no-install-recommends ffmpeg libavcodec-extra\n"
                         "Docs: https://ffmpeg.org/download.html\n"
                         "Support: +1 555 010 0199")

    def test_blurred_video_terminal(self):
        """A terminal inside a (slightly blurred) video frame."""
        here = os.path.dirname(os.path.abspath(__file__))
        result = engine.recognize(Image.open(os.path.join(here, "fixtures", "video-terminal.png")))
        self.assertEqual(result.text.splitlines(), [
            "$ sudo apt update",
            "Reading package lists... Done",
            "$ sudo apt install --no-install-recommends ffmpeg libavcodec-extra",
            "The following NEW packages will be installed:",
            "ffmpeg libavcodec-extra libavcodec-extra60",
            "Need to get 12.4 MB of archives. Continue? [Y/n]",
            "$ ffmpeg -i lecture.mkv -c:v libx264 -crf 20 lecture.mp4",
        ])

    def test_monospace_is_measured_from_word_boxes(self):
        mono = [engine.Word(t, 90, i * 100, 0, len(t) * 10, 12) for i, t in enumerate(["ffmpeg", "libx", "extra"])]
        self.assertTrue(engine.is_monospace(mono))
        prose = [engine.Word("illicit", 90, 0, 0, 30, 12), engine.Word("mammoth", 90, 40, 0, 80, 12),
                 engine.Word("will", 90, 130, 0, 14, 12)]
        self.assertFalse(engine.is_monospace(prose))

    def test_case_fix_leaves_prose_alone(self):
        words = [engine.Word("See", 90, 0, 0, 30, 12), engine.Word("Linux", 90, 40, 0, 45, 12)]
        engine.fix_code_case(words)
        self.assertEqual(words[1].text, "Linux")
        code = [engine.Word("sudo", 90, 0, 0, 36, 12), engine.Word("Libfoo-dev", 90, 45, 0, 90, 12)]
        engine.fix_code_case(code)
        self.assertEqual(code[1].text, "libfoo-dev")

    def test_touching_pieces_are_joined_only_at_punctuation(self):
        url = [engine.Word("download.", 90, 0, 0, 81, 12), engine.Word("html", 90, 82, 0, 36, 12)]
        engine.join_touching(url)
        self.assertEqual(engine.Line(url).text, "download.html")
        prose = [engine.Word("in", 90, 0, 0, 14, 12), engine.Word("it", 90, 15, 0, 10, 12)]
        engine.join_touching(prose)
        self.assertEqual(engine.Line(prose).text, "in it")

    def test_empty_region(self):
        result = engine.recognize(Image.new("RGB", (200, 60), (30, 30, 30)), "eng")
        self.assertEqual(result.text, "")

    def test_findings(self):
        text = "Visit https://example.com/track?id=42. Call +1 555 010 0199 or mail help@example.com"
        self.assertEqual(engine.findings(text), [
            ("link", "https://example.com/track?id=42"),
            ("email", "help@example.com"),
            ("phone", "+1 555 010 0199"),
        ])

    def test_short_numbers_are_not_phones(self):
        self.assertEqual(engine.findings("Version 2.0, page 12, 2026"), [])

    def test_crop_pads_and_stays_inside(self):
        shot = Image.new("RGB", (100, 100))
        region, x0, y0 = engine.crop(shot, 2, 2, 50, 50)
        self.assertEqual((x0, y0), (0, 0))
        self.assertEqual(region.size, (56, 56))


if __name__ == "__main__":
    unittest.main()
