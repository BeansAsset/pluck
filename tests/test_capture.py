"""The monitor and scale maths, for setups this machine doesn't have."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi  # noqa: E402

gi.require_version("Gdk", "3.0")
from pluck.capture import monitor_box  # noqa: E402


class MonitorBoxTest(unittest.TestCase):
    def test_one_ordinary_screen(self):
        self.assertEqual(monitor_box((1920, 1080), (0, 0, 1920, 1080), (0, 0, 1920, 1080)),
                         ((0, 0, 1920, 1080), 1.0))

    def test_hidpi_laptop_at_2x(self):
        # a 2880x1800 panel shown as 1440x900 logical pixels
        box, scale = monitor_box((2880, 1800), (0, 0, 1440, 900), (0, 0, 1440, 900))
        self.assertEqual(scale, 2.0)
        self.assertEqual(box, (0, 0, 2880, 1800))

    def test_fractional_scaling(self):
        # 2560x1440 at 150% is 1706.67x960 logical; desktops round to 1707x960
        box, scale = monitor_box((2560, 1440), (0, 0, 1707, 960), (0, 0, 1707, 960))
        self.assertAlmostEqual(scale, 1.4997, places=3)
        self.assertEqual(box, (0, 0, 2560, 1440))

    def test_second_monitor_on_the_right(self):
        # two 1920x1080 screens side by side; the pointer is on the right one
        box, scale = monitor_box((3840, 1080), (0, 0, 3840, 1080), (1920, 0, 1920, 1080))
        self.assertEqual((box, scale), ((1920, 0, 3840, 1080), 1.0))

    def test_monitor_left_of_the_primary(self):
        # a monitor placed at negative coordinates, to the left of the main one
        box, _scale = monitor_box((3840, 1080), (-1920, 0, 3840, 1080), (-1920, 0, 1920, 1080))
        self.assertEqual(box, (0, 0, 1920, 1080))


if __name__ == "__main__":
    unittest.main()
