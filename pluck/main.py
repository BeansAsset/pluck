"""Pluck: drag over anything on screen and get it as real text.

    pluck-app                 freeze the screen and start a selection
    pluck-app --background    just start, ready for the shortcut (used at login)

Only one Pluck runs; launching it again (e.g. from the keyboard shortcut)
tells the running one to capture. It stays running between uses so the
shortcut feels instant, and so text it copies stays on the clipboard.
"""

import os
import subprocess
import sys
import threading
import time
import urllib.parse

from .bridge import DEBUG, LATER, WebWindow  # sets up GTK and WebKit versions

from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, capture, engine, vertorama  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(GLib.get_user_cache_dir(), "pluck")
SEARCH = "https://duckduckgo.com/?q="


def log(*parts):
    if DEBUG:
        print("pluck:", *parts, flush=True)


class Overlay(WebWindow):
    """A full-screen window showing the frozen screen, drawn by web/."""

    def __init__(self, app):
        super().__init__(app, title=APP_NAME)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.frame = None         # capture.Frame: the frozen monitor, and its scale
        self.capturing = False
        self.pending_show = False
        self.connect("delete-event", lambda *_: self.hide() or True)

    # -- capture -------------------------------------------------------------------

    def start(self):
        """Freeze the screen and show it, once the page has drawn the image."""
        if self.get_visible() or self.capturing:
            return
        self.capturing = True
        # What's on screen right now, for Vertorama to find the window to scroll.
        self.stack = [] if capture.is_wayland() else vertorama.window_stack()
        log("capturing with", capture.method())
        capture.capture(self._captured, self._capture_failed)

    def _capture_failed(self, message):
        self.capturing = False
        self.app.notify("Pluck couldn't capture the screen", message)

    def _captured(self, frame):
        self.capturing = False
        self.frame = frame
        os.makedirs(CACHE, exist_ok=True)
        # A new name each time: local file URLs can't carry a ?query to
        # defeat caching, so the name itself has to change.
        for old in os.listdir(CACHE):
            if old.startswith("screen-"):
                try:
                    os.remove(os.path.join(CACHE, old))
                except OSError:
                    pass
        path = os.path.join(CACHE, f"screen-{time.time_ns()}.png")
        frame.image.save(path, compress_level=1)
        self.pending_show = True
        _x, _y, w, h = frame.logical
        shot = {"url": "file://" + urllib.parse.quote(path), "width": w, "height": h}
        log("captured", path, frame.image.size, "logical", frame.logical, "scale", frame.scale)
        if self.page_ready:
            self.emit("shot", shot)
        else:
            self._first_shot = shot

    def _show_now(self):
        log("drawn; showing" if self.pending_show else "drawn, nothing pending")
        if not self.pending_show:
            return
        self.pending_show = False
        x, y, w, h = self.frame.logical
        if not capture.is_wayland():
            self.move(x, y)
        self.resize(w, h)
        self.show_all()
        self.fullscreen_on_monitor(self.get_screen(), self.frame.monitor)
        self.present_with_time(Gtk.get_current_event_time() or Gdk.CURRENT_TIME)
        GLib.timeout_add(80, lambda: (self.get_window() and self.get_window().focus(Gdk.CURRENT_TIME), False)[1])

    # -- commands from the page ---------------------------------------------------------

    def cmd_ready(self, _id):
        self.page_ready = True
        shot = getattr(self, "_first_shot", None) if self.frame is not None else None
        return {"shot": shot, "vertorama": not capture.is_wayland()}

    def cmd_vertorama(self, _id, x, y, w, h):
        """Capture the whole scrolling area under a selection (page pixels)."""
        if capture.is_wayland():
            return {"error": "Vertorama scrolls for you on X11. Wayland support is coming."}
        frame = self.frame
        mx, my, _mw, _mh = frame.logical
        k = frame.scale
        region = (round((mx + x) * k), round((my + y) * k), round(w * k), round(h * k))
        logical = (mx + x, my + y, w, h)
        point = (mx + x + w / 2, my + y + h / 2)
        target = vertorama.window_at(self.stack, *point)
        self.cmd_close(None)
        # Closing the overlay can hand focus to some other window; the
        # Unroller puts the one that was under the selection back on top.
        GLib.timeout_add(250, lambda: (self.app.unroll(region, logical, target and target.get_xid(), point), False)[1])
        return True

    def cmd_drawn(self, _id):
        """The page has painted the frozen screen: safe to show the window."""
        self._show_now()

    def cmd_read(self, req_id, x, y, w, h):
        """OCR a region given in the page's (logical) pixels. Answers later,
        from a thread, with word boxes back in logical pixels."""
        frame = self.frame
        if frame is None or w < 4 or h < 4:
            return {"lines": [], "text": "", "findings": []}
        shot, k = frame.image, frame.scale

        def work():
            started = time.monotonic()
            try:
                region, x0, y0 = engine.crop(shot, x * k, y * k, w * k, h * k)
                result = engine.recognize(region)
                lines = [{"words": [{"text": wd.text, "x": (wd.x + x0) / k, "y": (wd.y + y0) / k,
                                     "w": wd.w / k, "h": wd.h / k, "conf": wd.conf, "space": wd.space}
                                    for wd in line.words]}
                         for line in result.lines]
                text = result.text
                out = {"lines": lines, "text": text, "findings": engine.findings(text),
                       "language": result.language, "ms": int((time.monotonic() - started) * 1000)}
            except (RuntimeError, OSError) as e:
                out = {"error": f"Couldn't read the text: {e}"}
            GLib.idle_add(lambda: (self.resolve(req_id, out), False)[1])
        threading.Thread(target=work, daemon=True).start()
        return LATER

    def cmd_copy(self, _id, text):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        return True

    def cmd_open(self, _id, kind, value):
        if kind == "search":
            uri = SEARCH + urllib.parse.quote_plus(value)
        elif kind == "email":
            uri = "mailto:" + value
        elif kind == "link":
            uri = value if "://" in value else "https://" + value
        else:
            return False
        self.cmd_close(None)
        Gio.AppInfo.launch_default_for_uri(uri, None)
        return True

    def cmd_close(self, _id):
        self.unfullscreen()
        self.hide()
        self.frame = None
        return True



class StatusPill(Gtk.Window):
    """A small note shown while Vertorama scrolls, placed outside the area
    being captured so it never ends up in the image."""

    def __init__(self, area):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.label = Gtk.Label(label="Vertorama · starting")
        css = Gtk.CssProvider()
        css.load_from_data(b"window { background: #18181a; border-radius: 10px; } "
                           b"label { color: #f4f2ef; font: 600 12.5px Inter, sans-serif; padding: 8px 14px; }")
        for widget in (self, self.label):
            widget.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.add(self.label)
        self.area = area

    def place(self):
        x, y, w, h = self.area
        self.show_all()
        pw, ph = self.get_size()
        screen_h = Gdk.Screen.get_default().get_height()
        if y - ph - 12 >= 0:
            top = y - ph - 12
        elif y + h + ph + 12 <= screen_h:
            top = y + h + 12
        else:
            self.hide()     # no room outside the area: stay out of the picture
            return
        self.move(int(x + (w - pw) / 2), int(top))

    def update(self, height, frames):
        self.label.set_text(f"Vertorama · {height:,} px · move the mouse to stop")


class ResultWindow(WebWindow):
    """The finished Vertorama: a preview, and save, copy, PDF, text."""
    page = "result.html"

    def __init__(self, app, image, reason):
        super().__init__(app, background=(0.063, 0.063, 0.071, 1), title="Vertorama")
        self.image = image
        self.reason = reason
        self.set_default_size(820, 760)
        self.set_icon_from_file(os.path.join(os.path.dirname(HERE), "data", APP_ID + ".svg"))
        os.makedirs(CACHE, exist_ok=True)
        self.preview = os.path.join(CACHE, f"vertorama-{time.time_ns()}.png")
        image.save(self.preview, compress_level=1)
        self.stamp = time.strftime("%Y-%m-%d %H.%M.%S")
        self.connect("destroy", lambda *_: os.path.exists(self.preview) and os.remove(self.preview))

    def _folder(self):
        pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) or os.path.expanduser("~/Pictures")
        folder = os.path.join(pictures, "Vertorama")
        os.makedirs(folder, exist_ok=True)
        return folder

    def _shown_folder(self):
        folder = self._folder()
        return f"{os.path.basename(os.path.dirname(folder))} › Vertorama"

    def cmd_ready(self, _id):
        self.page_ready = True
        return {"url": "file://" + urllib.parse.quote(self.preview), "width": self.image.width,
                "height": self.image.height, "reason": self.reason}

    def cmd_save_image(self, _id):
        path = os.path.join(self._folder(), f"Vertorama {self.stamp}.png")
        self.image.save(path)
        return {"path": path, "folder": self._shown_folder()}

    def _in_thread(self, req_id, work):
        def run():
            try:
                out = work()
            except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                out = {"error": str(e)}
            GLib.idle_add(lambda: (self.resolve(req_id, out), False)[1])
        threading.Thread(target=run, daemon=True).start()
        return LATER

    def cmd_save_pdf(self, req_id):
        path = os.path.join(self._folder(), f"Vertorama {self.stamp}.pdf")
        return self._in_thread(req_id, lambda: {"path": vertorama.save_pdf(self.image, path), "folder": self._shown_folder()})

    def cmd_copy_text(self, req_id):
        def work():
            text = vertorama.text_of(self.image)
            GLib.idle_add(lambda: (Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1), False)[1])
            return {"chars": len(text)}
        return self._in_thread(req_id, work)

    def cmd_copy_image(self, _id):
        from gi.repository import GdkPixbuf
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.preview)
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_image(pixbuf)
        return True

    def cmd_show(self, _id, path):
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        try:
            bus.call_sync("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                          "org.freedesktop.FileManager1", "ShowItems",
                          GLib.Variant("(ass)", ([Gio.File.new_for_path(path).get_uri()], "")),
                          None, Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error:
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(os.path.dirname(path)).get_uri(), None)

    def cmd_close(self, _id):
        self.destroy()


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.overlay = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
        self.hold()   # stay running: instant next time, and copied text survives
        self.overlay = Overlay(self)

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if "--background" not in args:
            # Let the launching key press finish before freezing the screen.
            GLib.timeout_add(120, lambda: (self.overlay.start(), False)[1])
        return 0

    def unroll(self, region, logical, target=None, point=None):
        """Run Vertorama over a region of the screen."""
        from .vertorama import Unroller
        pill = StatusPill(logical)
        pill.place()

        def done(image, reason):
            pill.destroy()
            result = ResultWindow(self, image, reason)
            result.show_all()
            result.present_with_time(vertorama.server_time(result.get_window()))
        try:
            Unroller(region, done, pill.update, target, point).start()
        except Exception as e:  # e.g. python-xlib missing
            pill.destroy()
            self.notify("Vertorama couldn't start", str(e))

    def notify(self, title, body):
        note = Gio.Notification.new(title)
        icon = os.path.join(os.path.dirname(HERE), "data", "io.github.beansasset.Pluck.svg")
        if os.path.exists(icon):
            note.set_icon(Gio.FileIcon.new(Gio.File.new_for_path(icon)))
        note.set_body(body)
        self.send_notification(None, note)


def main():
    return Application().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
