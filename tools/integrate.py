"""Set Pluck up for the current user, on whichever desktop and distro this is.

    python3 tools/integrate.py install    menu entry, login item, shortcut
    python3 tools/integrate.py remove     undo all of it
    python3 tools/integrate.py check      only check what's missing

Never uses sudo. If something Pluck needs is missing, it prints the command
for this distro's package manager and stops.
"""

import ast
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "io.github.beansasset.Pluck"
NAME = "Pluck"
COMMAND = os.path.join(HERE, "pluck-app")
SHORTCUT_NAME = "pluck"
BINDING = {   # Super+Shift+T, in each desktop's own notation
    "gsettings": "<Super><Shift>t",
    "xfce": "<Super><Shift>t",
    "kde": "Meta+Shift+T",
}

HOME = os.path.expanduser("~")
DATA = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
APPS_FILE = os.path.join(DATA, "applications", APP_ID + ".desktop")
AUTOSTART_FILE = os.path.join(CONFIG, "autostart", APP_ID + ".desktop")
ICON_FILE = os.path.join(DATA, "icons", "hicolor", "scalable", "apps", APP_ID + ".svg")


# -- what this system is ----------------------------------------------------------

def read_os_release(path="/etc/os-release"):
    info = {}
    try:
        with open(path) as f:
            for line in f:
                if "=" in line:
                    key, _, value = line.strip().partition("=")
                    info[key] = value.strip('"')
    except OSError:
        pass
    return info


def distro_family(os_release):
    ids = [os_release.get("ID", "")] + os_release.get("ID_LIKE", "").split()
    for family, members in (("debian", {"debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin"}),
                            ("fedora", {"fedora", "rhel", "centos", "nobara"}),
                            ("arch", {"arch", "manjaro", "endeavouros", "garuda"}),
                            ("suse", {"opensuse", "suse", "opensuse-tumbleweed", "opensuse-leap"})):
        if any(i in members for i in ids):
            return family
    return None


PACKAGES = {
    # what Pluck needs -> package name in each family
    "debian": {"tesseract": "tesseract-ocr", "gi": "python3-gi", "pil": "python3-pil",
               "gtk": "gir1.2-gtk-3.0", "webkit": "gir1.2-webkit2-4.1", "xlib": "python3-xlib"},
    "fedora": {"tesseract": "tesseract tesseract-langpack-eng", "gi": "python3-gobject", "pil": "python3-pillow",
               "gtk": "gtk3", "webkit": "webkit2gtk4.1", "xlib": "python3-xlib"},
    "arch": {"tesseract": "tesseract tesseract-data-eng", "gi": "python-gobject", "pil": "python-pillow",
             "gtk": "gtk3", "webkit": "webkit2gtk-4.1", "xlib": "python-xlib"},
    "suse": {"tesseract": "tesseract-ocr tesseract-ocr-traineddata-english", "gi": "python3-gobject",
             "pil": "python3-Pillow", "gtk": "typelib-1_0-Gtk-3_0", "webkit": "typelib-1_0-WebKit2-4_1", "xlib": "python3-python-xlib"},
}
INSTALL = {"debian": "sudo apt install", "fedora": "sudo dnf install",
           "arch": "sudo pacman -S --needed", "suse": "sudo zypper install"}


def install_command(family, missing):
    if family not in PACKAGES or not missing:
        return None
    names = " ".join(PACKAGES[family][m] for m in missing)
    return f"{INSTALL[family]} {names}"


def missing_requirements():
    missing = []
    if not shutil.which("tesseract"):
        missing.append("tesseract")
    else:
        langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
        if "eng" not in langs.split():
            missing.append("tesseract")
    try:
        import gi
    except ImportError:
        return missing + ["gi", "gtk", "webkit"] + ([] if _has_pil() else ["pil"])
    try:
        gi.require_version("Gtk", "3.0")
    except ValueError:
        missing.append("gtk")
    for version in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", version)
            break
        except ValueError:
            continue
    else:
        missing.append("webkit")
    if not _has_pil():
        missing.append("pil")
    if os.environ.get("XDG_SESSION_TYPE") != "wayland" and not _has_xlib():
        missing.append("xlib")     # Vertorama scrolls other windows through it (X11)
    return missing


def _has_xlib():
    try:
        import Xlib  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pil():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def desktop(env=None):
    """Which desktop's shortcut system to use."""
    env = os.environ if env is None else env
    current = env.get("XDG_CURRENT_DESKTOP", "").lower().split(":")
    session = env.get("DESKTOP_SESSION", "").lower()
    names = set(current) | {session}
    if names & {"x-cinnamon", "cinnamon"}:
        return "cinnamon"
    if "kde" in names or "plasma" in session:
        return "kde"
    if "xfce" in names or "xfce" in session:
        return "xfce"
    if "mate" in names:
        return "mate"
    if names & {"gnome", "ubuntu", "budgie", "budgie-desktop", "pantheon", "unity", "pop", "cosmic"}:
        return "gnome"
    return None


# -- files: menu entry, icon, login item ----------------------------------------------

def write_files():
    os.makedirs(os.path.dirname(APPS_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(ICON_FILE), exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "data", APP_ID + ".svg"), ICON_FILE)
    with open(APPS_FILE, "w") as f:
        f.write(f"""[Desktop Entry]
Type=Application
Name={NAME}
Comment=Copy text from anything on your screen
Exec={COMMAND}
Icon={APP_ID}
Categories=Utility;
Keywords=ocr;text;copy;screen;screenshot;lens;extract;
StartupNotify=false
""")
    with open(AUTOSTART_FILE, "w") as f:
        f.write(f"""[Desktop Entry]
Type=Application
Name={NAME}
Comment=Ready for Super+Shift+T
Exec={COMMAND} --background
Icon={APP_ID}
X-GNOME-Autostart-enabled=true
NoDisplay=true
""")


def remove_files():
    for path in (APPS_FILE, AUTOSTART_FILE, ICON_FILE):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# -- shortcuts, one desktop at a time ---------------------------------------------------

def _gs(*args, check=True):
    return subprocess.run(["gsettings", *args], capture_output=True, text=True, check=check).stdout.strip()


def _gs_list(schema, key):
    raw = _gs("get", schema, key)
    return ast.literal_eval(raw.replace("@as ", "")) if raw else []


def cinnamon(add):
    base = "org.cinnamon.desktop.keybindings"
    path = f"/org/cinnamon/desktop/keybindings/custom-keybindings/{SHORTCUT_NAME}/"
    schema = f"{base}.custom-keybinding:{path}"
    items = [i for i in _gs_list(base, "custom-list") if i != SHORTCUT_NAME]
    if add:
        _gs("set", schema, "name", NAME)
        _gs("set", schema, "command", COMMAND)
        _gs("set", schema, "binding", str([BINDING["gsettings"]]))
        items.append(SHORTCUT_NAME)
    else:
        _gs("reset-recursively", schema, check=False)
    _gs("set", base, "custom-list", str(items))


def gnome(add):
    base = "org.gnome.settings-daemon.plugins.media-keys"
    path = f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/{SHORTCUT_NAME}/"
    schema = f"{base}.custom-keybinding:{path}"
    items = [i for i in _gs_list(base, "custom-keybindings") if i != path]
    if add:
        _gs("set", schema, "name", NAME)
        _gs("set", schema, "command", COMMAND)
        _gs("set", schema, "binding", BINDING["gsettings"])
        items.append(path)
    else:
        _gs("reset-recursively", schema, check=False)
    _gs("set", base, "custom-keybindings", str(items))


def mate(add):
    path = f"/org/mate/desktop/keybindings/{SHORTCUT_NAME}/"
    schema = f"org.mate.control-center.keybinding:{path}"
    if add:
        _gs("set", schema, "name", NAME)
        _gs("set", schema, "action", COMMAND)
        _gs("set", schema, "binding", BINDING["gsettings"])
    else:
        _gs("reset-recursively", schema, check=False)


def xfce(add):
    prop = f"/commands/custom/{BINDING['xfce']}"
    if add:
        subprocess.run(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", prop, "-n",
                        "-t", "string", "-s", COMMAND], check=True)
    else:
        subprocess.run(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", prop, "-r"], check=False)


def kde(add):
    # KDE keeps launcher shortcuts in kglobalshortcutsrc, keyed by the
    # .desktop file. Plasma reads it at login.
    tool = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    if not tool:
        raise RuntimeError("kwriteconfig6 not found")
    group = ["--file", "kglobalshortcutsrc", "--group", "services", "--group", APP_ID + ".desktop"]
    if add:
        subprocess.run([tool, *group, "--key", "_launch", BINDING["kde"]], check=True)
    else:
        subprocess.run([tool, *group, "--key", "_launch", "--delete"], check=False)


SHORTCUTS = {"cinnamon": cinnamon, "gnome": gnome, "mate": mate, "xfce": xfce, "kde": kde}


# -- commands ------------------------------------------------------------------------------

def check():
    missing = missing_requirements()
    if not missing:
        return True
    family = distro_family(read_os_release())
    cmd = install_command(family, missing)
    print(f"{NAME} needs a few things first.")
    if cmd:
        print(f"Install them with:\n\n    {cmd}\n")
    else:
        print("Install these with your package manager: Tesseract OCR with English, Python GObject, "
              "Pillow, GTK 3, WebKitGTK (4.1 or 4.0) and, on X11, python-xlib.")
    print("Then run this again.")
    return False


def install():
    if not check():
        return 1
    write_files()
    print(f"Added {NAME} to your apps menu, and set it to start quietly at login.")
    where = desktop()
    if where in SHORTCUTS:
        try:
            SHORTCUTS[where](True)
            note = " (takes effect after you log out and back in)" if where == "kde" else ""
            print(f"Super+Shift+T now opens {NAME}{note}. Super is the Windows key.")
        except (OSError, RuntimeError, subprocess.CalledProcessError) as e:
            print(f"Couldn't set the shortcut automatically ({e}).")
            print(f"Add one in your keyboard settings that runs: {COMMAND}")
    else:
        print(f"Add a shortcut in your keyboard settings that runs: {COMMAND}")
    subprocess.Popen([COMMAND, "--background"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return 0


def remove():
    remove_files()
    where = desktop()
    if where in SHORTCUTS:
        try:
            SHORTCUTS[where](False)
        except (OSError, RuntimeError, subprocess.CalledProcessError):
            pass
    print(f"Removed {NAME}'s menu entry, login item and shortcut.")
    return 0


def main(argv):
    action = argv[1] if len(argv) > 1 else "install"
    if action == "install":
        return install()
    if action == "remove":
        return remove()
    if action == "check":
        return 0 if check() else 1
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
