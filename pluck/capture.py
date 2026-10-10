"""Takes the screenshot Pluck freezes and reads from.

Two ways, chosen at runtime:

  * X11 (Linux Mint, older distros): read the screen directly. Instant, and
    no prompts.
  * Wayland (GNOME, KDE and most newer distros), or when the direct way
    fails: ask the desktop's screenshot portal
    (org.freedesktop.portal.Screenshot). This is the standard, cross-desktop
    way. Some desktops ask the first time whether Pluck may take
    screenshots.

Either way the result is cut down to the monitor under the pointer, with the
scale between that monitor's logical size (what windows and the page use)
and its real pixels, so HiDPI and fractional scaling line up.

PLUCK_CAPTURE=portal forces the portal, for testing it on X11.
"""

import os
import secrets
import urllib.parse
from dataclasses import dataclass

from gi.repository import Gdk, Gio, GLib
from PIL import Image

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"


@dataclass
class Frame:
    image: object          # PIL image of one monitor, in real pixels
    monitor: int           # GDK monitor index
    logical: tuple         # (x, y, width, height) of that monitor, logical pixels
    scale: float           # real pixels per logical pixel


def is_wayland():
    display = Gdk.Display.get_default()
    if display is not None and type(display).__name__.startswith("GdkWayland"):
        return True
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def method():
    if os.environ.get("PLUCK_CAPTURE") == "portal" or is_wayland():
        return "portal"
    return "x11"


def monitor_under_pointer():
    display = Gdk.Display.get_default()
    _screen, x, y = display.get_default_seat().get_pointer().get_position()
    monitor = display.get_monitor_at_point(x, y) or display.get_primary_monitor() or display.get_monitor(0)
    index = next(i for i in range(display.get_n_monitors()) if display.get_monitor(i) == monitor)
    g = monitor.get_geometry()
    return index, (g.x, g.y, g.width, g.height)


def desktop_bounds():
    """The logical rectangle covering every monitor."""
    display = Gdk.Display.get_default()
    rects = [display.get_monitor(i).get_geometry() for i in range(display.get_n_monitors())]
    x0 = min(r.x for r in rects)
    y0 = min(r.y for r in rects)
    x1 = max(r.x + r.width for r in rects)
    y1 = max(r.y + r.height for r in rects)
    return x0, y0, x1 - x0, y1 - y0


def monitor_box(image_size, bounds, monitor):
    """Where one monitor sits inside a whole-desktop screenshot.

    image_size: (width, height) of the screenshot, in real pixels
    bounds:     (x, y, width, height) of the whole desktop, logical pixels
    monitor:    (x, y, width, height) of the monitor, logical pixels
    Returns (crop box in real pixels, real pixels per logical pixel).
    """
    bx, by, bw, _bh = bounds
    mx, my, mw, mh = monitor
    scale = image_size[0] / bw if bw else 1.0
    box = (round((mx - bx) * scale), round((my - by) * scale),
           round((mx - bx + mw) * scale), round((my - by + mh) * scale))
    return box, scale


def to_frame(full):
    """Cut a whole-desktop screenshot down to the monitor under the pointer."""
    index, monitor = monitor_under_pointer()
    box, scale = monitor_box(full.size, desktop_bounds(), monitor)
    image = full.crop(box) if box != (0, 0, full.width, full.height) else full
    return Frame(image=image, monitor=index, logical=monitor, scale=scale)


# -- X11 -------------------------------------------------------------------------

def capture_x11():
    root = Gdk.get_default_root_window()
    if root is None:
        raise RuntimeError("no root window")
    scale = root.get_scale_factor()
    w, h = root.get_width(), root.get_height()
    pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, w, h)
    if pixbuf is None:
        raise RuntimeError("couldn't read the screen")
    mode = "RGBA" if pixbuf.get_has_alpha() else "RGB"
    image = Image.frombytes(mode, (pixbuf.get_width(), pixbuf.get_height()),
                            pixbuf.get_pixels(), "raw", mode, pixbuf.get_rowstride()).convert("RGB")
    if scale > 1 and image.width == w:   # some setups hand back logical pixels
        image = image.resize((w * scale, h * scale), Image.LANCZOS)
    return image


# -- the screenshot portal --------------------------------------------------------

class PortalCapture:
    """One non-interactive screenshot through the portal. Calls
    on_done(PIL image) or on_error(message) on the main loop."""

    def __init__(self, on_done, on_error):
        self.on_done, self.on_error = on_done, on_error
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.subscription = None

    def start(self):
        token = "pluck" + secrets.token_hex(6)
        sender = self.bus.get_unique_name()[1:].replace(".", "_")
        request_path = f"{PORTAL_PATH}/request/{sender}/{token}"
        # Listen before asking, so a fast answer can't be missed.
        self.subscription = self.bus.signal_subscribe(
            PORTAL, "org.freedesktop.portal.Request", "Response", request_path,
            None, Gio.DBusSignalFlags.NO_MATCH_RULE, self._on_response)
        options = {"handle_token": GLib.Variant("s", token), "interactive": GLib.Variant("b", False)}
        self.bus.call(PORTAL, PORTAL_PATH, "org.freedesktop.portal.Screenshot", "Screenshot",
                      GLib.Variant("(sa{sv})", ("", options)), GLib.VariantType("(o)"),
                      Gio.DBusCallFlags.NONE, -1, None, self._on_called)

    def _on_called(self, bus, result):
        try:
            bus.call_finish(result)
        except GLib.Error as e:
            self._finish()
            self.on_error(f"The screenshot portal isn't available ({e.message}).")

    def _on_response(self, _bus, _sender, _path, _iface, _signal, params):
        code, results = params.unpack()
        self._finish()
        if code == 1:
            self.on_error("Taking the screenshot was cancelled.")
            return
        if code != 0 or "uri" not in results:
            self.on_error("The desktop didn't allow a screenshot.")
            return
        path = urllib.parse.unquote(urllib.parse.urlparse(results["uri"]).path)
        try:
            with Image.open(path) as im:
                image = im.convert("RGB")
        except OSError as e:
            self.on_error(f"Couldn't open the screenshot: {e}")
            return
        finally:
            # The portal saves a file for us; it was only ever ours to read.
            try:
                os.remove(path)
            except OSError:
                pass
        self.on_done(image)

    def _finish(self):
        if self.subscription is not None:
            self.bus.signal_unsubscribe(self.subscription)
            self.subscription = None


def capture(on_done, on_error):
    """Take a screenshot of the monitor under the pointer: on_done(Frame)."""
    if method() == "x11":
        try:
            on_done(to_frame(capture_x11()))
            return
        except RuntimeError:
            pass   # fall back to the portal
    PortalCapture(lambda image: on_done(to_frame(image)), on_error).start()
