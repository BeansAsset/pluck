"""The installer's choices, for distros and desktops this machine isn't."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import integrate  # noqa: E402

OS_RELEASE = {
    "Linux Mint 22": 'NAME="Linux Mint"\nID=linuxmint\nID_LIKE="ubuntu debian"\n',
    "Ubuntu 24.04": 'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\n',
    "Debian 12": 'NAME="Debian GNU/Linux"\nID=debian\n',
    "Fedora 41": 'NAME="Fedora Linux"\nID=fedora\n',
    "Arch": 'NAME="Arch Linux"\nID=arch\n',
    "Manjaro": 'NAME="Manjaro Linux"\nID=manjaro\nID_LIKE=arch\n',
    "openSUSE Tumbleweed": 'NAME="openSUSE Tumbleweed"\nID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n',
    "Pop!_OS": 'NAME="Pop!_OS"\nID=pop\nID_LIKE="ubuntu debian"\n',
    "Alpine": 'NAME="Alpine Linux"\nID=alpine\n',
}


def family_of(name):
    with tempfile.NamedTemporaryFile("w", suffix="os-release", delete=False) as f:
        f.write(OS_RELEASE[name])
    try:
        return integrate.distro_family(integrate.read_os_release(f.name))
    finally:
        os.remove(f.name)


class DistroTest(unittest.TestCase):
    def test_families(self):
        expected = {"Linux Mint 22": "debian", "Ubuntu 24.04": "debian", "Debian 12": "debian",
                    "Fedora 41": "fedora", "Arch": "arch", "Manjaro": "arch",
                    "openSUSE Tumbleweed": "suse", "Pop!_OS": "debian", "Alpine": None}
        for name, family in expected.items():
            self.assertEqual(family_of(name), family, name)

    def test_install_commands(self):
        self.assertEqual(integrate.install_command("debian", ["tesseract", "webkit"]),
                         "sudo apt install tesseract-ocr gir1.2-webkit2-4.1")
        self.assertEqual(integrate.install_command("arch", ["tesseract"]),
                         "sudo pacman -S --needed tesseract tesseract-data-eng")
        self.assertEqual(integrate.install_command("fedora", ["pil"]), "sudo dnf install python3-pillow")
        self.assertIsNone(integrate.install_command(None, ["pil"]))
        self.assertIsNone(integrate.install_command("debian", []))


class DesktopTest(unittest.TestCase):
    def test_desktops(self):
        cases = {
            ("X-Cinnamon", "cinnamon"): "cinnamon",
            ("ubuntu:GNOME", "ubuntu"): "gnome",
            ("GNOME", "gnome"): "gnome",
            ("Budgie:GNOME", "budgie-desktop"): "gnome",
            ("pop:GNOME", "pop"): "gnome",
            ("KDE", "plasma"): "kde",
            ("XFCE", "xfce"): "xfce",
            ("MATE", "mate"): "mate",
            ("sway", "sway"): None,
            ("", ""): None,
        }
        for (current, session), expected in cases.items():
            env = {"XDG_CURRENT_DESKTOP": current, "DESKTOP_SESSION": session}
            self.assertEqual(integrate.desktop(env), expected, current)


if __name__ == "__main__":
    unittest.main()
