"""Stitching tests: a known long page, cut into frames as a scrolling window
would show it, must come back out pixel for pixel."""

import os
import random
import sys
import unittest

from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pluck import stitch  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
W = 420


def long_page(lines=160):
    """A tall 'conversation' with varied lines, so every part is distinct."""
    f = ImageFont.truetype(FONT, 14)
    rng = random.Random(7)
    words = "send the photos from the trip tomorrow morning okay sure sounds good see you then".split()
    page = Image.new("RGB", (W, lines * 26 + 20), (24, 24, 28))
    d = ImageDraw.Draw(page)
    for i in range(lines):
        text = f"{i + 1:03d}  " + " ".join(rng.choice(words) for _ in range(rng.randint(2, 7)))
        x = 20 if i % 3 else 120   # alternate sides like chat bubbles
        d.text((x, 10 + i * 26), text, font=f, fill=(225, 225, 230))
    return page


def window(page, scroll, height=360, header=40, footer=50):
    """What the window shows when scrolled to `scroll`: a fixed title bar,
    the visible part of the page, a fixed message box."""
    body = height - header - footer
    frame = Image.new("RGB", (W, height), (40, 40, 46))
    ImageDraw.Draw(frame).text((16, 12), "Chat with Sam", font=ImageFont.truetype(FONT, 15), fill=(255, 255, 255))
    frame.paste(page.crop((0, scroll, W, scroll + body)), (0, header))
    ImageDraw.Draw(frame).rectangle((10, height - footer + 10, W - 10, height - 10), fill=(60, 60, 68))
    return frame


def expected(page, height=360, header=40, footer=50):
    """The ideal result: title bar once, the whole page, message box once."""
    body = height - header - footer
    end = page.height - body
    top = window(page, 0, height, header, footer).crop((0, 0, W, header))
    bottom = window(page, end, height, header, footer).crop((0, height - footer, W, height))
    out = Image.new("RGB", (W, header + page.height + footer))
    out.paste(top, (0, 0))
    out.paste(page, (0, header))
    out.paste(bottom, (0, header + page.height))
    return out


def run(frames):
    s = stitch.Stitcher()
    shifts = [s.add(f) for f in frames]
    return s, shifts


def same(a, b):
    return a.size == b.size and ImageChops.difference(a, b).getbbox() is None


class StitchTest(unittest.TestCase):
    def setUp(self):
        self.page = long_page()
        self.end = self.page.height - (360 - 40 - 50)

    def scrolls(self, steps):
        out, y = [0], 0
        for step in steps:
            y = min(self.end, y + step)
            out.append(y)
        return out

    def test_steady_scrolling_rebuilds_the_page_exactly(self):
        positions = self.scrolls([120] * 60)
        s, shifts = run([window(self.page, y) for y in positions])
        self.assertIn(0, shifts)                      # the end was noticed
        self.assertTrue(same(s.result(), expected(self.page)))

    def test_uneven_steps_like_smooth_scrolling(self):
        rng = random.Random(3)
        positions = self.scrolls([rng.randint(30, 200) for _ in range(80)])
        s, _ = run([window(self.page, y) for y in positions])
        self.assertTrue(same(s.result(), expected(self.page)))

    def test_fixed_header_and_footer_are_kept_once(self):
        positions = self.scrolls([150] * 40)
        s, _ = run([window(self.page, y) for y in positions])
        # At least the real bars; blank page rows touching them may join in,
        # which is harmless because the result is still exact.
        self.assertGreaterEqual(s.header, 40)
        self.assertGreaterEqual(s.footer, 50)
        self.assertLess(s.header + s.footer, 120)
        self.assertTrue(same(s.result(), expected(self.page)))

    def test_blinking_cursor_in_the_message_box(self):
        positions = self.scrolls([110] * 50)
        frames = []
        for k, y in enumerate(positions):
            f = window(self.page, y)
            if k % 2:   # cursor on in every other frame
                ImageDraw.Draw(f).rectangle((24, 360 - 34, 26, 360 - 18), fill=(255, 255, 255))
            frames.append(f)
        s, shifts = run(frames)
        self.assertNotIn(None, shifts)
        self.assertEqual(s.result().height, 40 + self.page.height + 50)

    def test_animated_picture_inside_the_content(self):
        """A GIF in the conversation scrolls with it but changes every frame;
        it must not stop the matching."""
        positions = self.scrolls([100] * 60)
        frames = []
        for k, y in enumerate(positions):
            f = window(self.page, y)
            top = 40 + 800 - y          # the GIF sits at y=800 on the page
            if -40 < top < 310:
                box = (260, max(40, top), 380, min(310, top + 40))
                if box[3] > box[1]:
                    ImageDraw.Draw(f).rectangle(box, fill=(k * 37 % 255, 90, 160))
            frames.append(f)
        s, shifts = run(frames)
        self.assertNotIn(None, shifts)
        self.assertEqual(s.result().height, 40 + self.page.height + 50)

    def test_scroll_edge_line_does_not_repeat_at_every_join(self):
        """Many themes draw a dashed 'more below' line at the bottom of a
        scrolled area while there's more to see. It must not end up in the
        middle of the result, once per join."""
        positions = self.scrolls([120] * 60)
        frames = []
        for y in positions:
            f = window(self.page, y)
            if y < self.end:
                d = ImageDraw.Draw(f)
                for x in range(0, W, 8):
                    d.line((x, 360 - 50 - 1, x + 3, 360 - 50 - 1), fill=(200, 200, 200))
            frames.append(f)
        s, _ = run(frames)
        self.assertTrue(same(s.result(), expected(self.page)))

    def test_too_big_a_jump_is_refused_not_guessed(self):
        """No overlap at all: say so instead of gluing unrelated frames."""
        s = stitch.Stitcher()
        s.add(window(self.page, 0))
        self.assertIsNone(s.add(window(self.page, 900)))

    def test_nothing_moved(self):
        s = stitch.Stitcher()
        s.add(window(self.page, 0))
        self.assertEqual(s.add(window(self.page, 0)), 0)

    def test_fingerprints_ignore_tiny_rendering_differences(self):
        a = window(self.page, 0)
        b = Image.eval(a, lambda v: min(255, v + 2))   # a hair brighter everywhere
        self.assertEqual(stitch.fingerprints(a)[100], stitch.fingerprints(b)[100])


class PagesTest(unittest.TestCase):
    def test_pages_are_cut_between_lines(self):
        from pluck import vertorama
        page = long_page(120)
        parts = vertorama.pages(page, 500)
        self.assertEqual(sum(p.height for p in parts), page.height)
        # Text sits on rows 2..15 of every 26-row line (from y=10). A cut
        # between rows y-1 and y must have no ink on either side.
        gray = page.convert("L")
        def inked(row):
            return gray.crop((0, row, gray.width, row + 1)).getextrema()[1] > 60
        y = 0
        for part in parts[:-1]:
            y += part.height
            self.assertFalse(inked(y - 1) or inked(y), f"cut at {y} runs through a line")


if __name__ == "__main__":
    unittest.main()
