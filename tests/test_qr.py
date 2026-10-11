"""QR codes on screen: finding them, and describing what's in them safely."""

import os
import sys
import unittest

from PIL import Image, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pluck import qr  # noqa: E402


def make(data, box=6, size=(900, 600), at=(120, 80), dark=False):
    """A screen-like image with a QR code drawn on it."""
    import qrcode
    code = qrcode.make(data, box_size=box, border=2).convert("L")
    screen = Image.new("L", size, 240)
    screen.paste(code, at)
    return ImageOps.invert(screen) if dark else screen


@unittest.skipUnless(qr.available(), "libzbar isn't installed")
class FindTest(unittest.TestCase):
    def test_finds_a_code_and_where_it_is(self):
        codes = qr.find(make("https://github.com/BeansAsset/pluck"))
        self.assertEqual(len(codes), 1)
        c = codes[0]
        self.assertEqual(c.data, "https://github.com/BeansAsset/pluck")
        self.assertTrue(110 <= c.x <= 150 and 70 <= c.y <= 110, (c.x, c.y))
        self.assertGreater(c.w, 100)

    def test_small_code_like_a_video_corner(self):
        codes = qr.find(make("https://example.org/slides", box=2))
        self.assertEqual([c.data for c in codes], ["https://example.org/slides"])

    def test_light_on_dark(self):
        codes = qr.find(make("hello from dark mode", dark=True))
        self.assertEqual([c.data for c in codes], ["hello from dark mode"])

    def test_two_codes(self):
        screen = make("first", at=(40, 40))
        screen.paste(make("second", size=(300, 300), at=(20, 20)).crop((0, 0, 300, 300)), (560, 260))
        self.assertEqual(sorted(c.data for c in qr.find(screen)), ["first", "second"])

    def test_nothing_there(self):
        self.assertEqual(qr.find(Image.new("RGB", (800, 500), (250, 250, 250))), [])


class DescribeTest(unittest.TestCase):
    def test_link_shows_whose_site_it_really_is(self):
        d = qr.describe("https://paypal.com.secure-login.xyz/verify")
        self.assertEqual(d["kind"], "link")
        self.assertEqual(d["site"], "secure-login.xyz")
        self.assertTrue(d["secure"])

    def test_country_domains(self):
        self.assertEqual(qr.site_of("shop.example.co.uk"), "example.co.uk")
        self.assertEqual(qr.site_of("www.github.com"), "github.com")

    def test_plain_http_and_lookalike_letters_are_flagged(self):
        self.assertFalse(qr.describe("http://example.com")["secure"])
        self.assertTrue(qr.describe("https://xn--pypal-4ve.com/")["unusual"])

    def test_wifi(self):
        d = qr.describe(r"WIFI:T:WPA;S:Cafe\;Guest;P:pa\:ss;;")
        self.assertEqual((d["network"], d["password"], d["security"]), ("Cafe;Guest", "pa:ss", "WPA"))

    def test_other_kinds(self):
        self.assertEqual(qr.describe("mailto:hi@example.com?subject=x"), {"kind": "email", "value": "hi@example.com"})
        self.assertEqual(qr.describe("tel:+15551234567")["kind"], "phone")
        self.assertEqual(qr.describe("just some text")["kind"], "text")


if __name__ == "__main__":
    unittest.main()
