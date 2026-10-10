"""Pluck: drag over anything on screen and get it as real text.

    pluck-app                 freeze the screen and start a selection
    pluck-app --background    just start, ready for the shortcut (used at login)

Only one Pluck runs; launching it again (e.g. from the keyboard shortcut)
tells the running one to capture. It stays running between uses so the
shortcut feels instant, and so text it copies stays on the clipboard.
"""

import json
import os
import sys
import threading
import time
import urllib.parse

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2  # noqa: E402

from PIL import Image  # noqa: E402

from . import APP_ID, APP_NAME, engine  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
CACHE = os.path.join(GLib.get_user_cache_dir(), "pluck")
DEBUG = bool(os.environ.get("PLUCK_DEBUG"))
SEARCH = "https://duckduckgo.com/?q="


def log(*parts):
    if DEBUG:
        print("pluck:", *parts, flush=True)


def capture_screen():
    """The whole screen as a PIL image, taken before Pluck shows anything."""
    root = Gdk.get_default_root_window()
    w, h = root.get_width(), root.get_height()
    pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, w, h)
    if pixbuf is None:
        raise RuntimeError("couldn't capture the screen")
    mode = "RGBA" if pixbuf.get_has_alpha() else "RGB"
    image = Image.frombytes(mode, (w, h), pixbuf.get_pixels(), "raw", mode, pixbuf.get_rowstride())
    return image.convert("RGB")


class Overlay(Gtk.Window):
    """A full-screen window showing the frozen screen, drawn by web/."""

    def __init__(self, app):
        super().__init__(title=APP_NAME)
        self.app = app
        self.set_application(app)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.shot = None          # PIL image of the frozen screen
        self.page_ready = False
        self.pending_show = False
        self.view = self._make_view()
        self.add(self.view)
        self.connect("delete-event", lambda *_: self.hide() or True)

    def _make_view(self):
        ucm = WebKit2.UserContentManager()
        ucm.register_script_message_handler("pluck")
        ucm.connect("script-message-received::pluck", self._on_message)
        view = WebKit2.WebView(user_content_manager=ucm)
        s = view.get_settings()
        s.set_allow_file_access_from_file_urls(True)
        s.set_enable_developer_extras(DEBUG)
        s.set_enable_write_console_messages_to_stdout(DEBUG)
        s.set_javascript_can_open_windows_automatically(False)
        s.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        view.set_background_color(Gdk.RGBA(0, 0, 0, 1))
        view.connect("decide-policy", self._on_policy)
        view.connect("context-menu", lambda *_: not DEBUG)
        view.load_uri("file://" + os.path.join(WEB, "index.html"))
        return view

    def _on_policy(self, _view, decision, kind):
        if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
            if not uri.startswith("file://" + WEB):
                decision.ignore()
                return True
        elif kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            decision.ignore()
            return True
        return False

    # -- bridge --------------------------------------------------------------

    def emit(self, name, data=None):
        if self.page_ready:
            self.view.evaluate_javascript(
                f"Pluck.emit({json.dumps(name)}, {json.dumps(data)})", -1, None, None, None, None, None)

    def _resolve(self, req_id, result):
        self.view.evaluate_javascript(
            f"Pluck.resolve({json.dumps(req_id)}, {json.dumps(result)})", -1, None, None, None, None, None)

    def _on_message(self, _ucm, js_result):
        msg = {}
        try:
            msg = json.loads(js_result.get_js_value().to_json(0))
            handler = getattr(self, "cmd_" + msg.get("cmd", "").replace("-", "_"))
            result = handler(msg.get("id"), *msg.get("args", []))
        except Exception as e:  # report to the page instead of crashing
            if DEBUG:
                raise
            result = {"error": str(e)}
        if msg.get("id") is not None and result is not LATER:
            self._resolve(msg["id"], result)

    # -- capture -------------------------------------------------------------------

    def start(self):
        """Freeze the screen and show it, once the page has drawn the image."""
        if self.get_visible():
            return
        try:
            self.shot = capture_screen()
        except RuntimeError as e:
            self.app.notify("Pluck couldn't capture the screen", str(e))
            return
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
        self.shot.save(path, compress_level=1)
        self.pending_show = True
        url = "file://" + urllib.parse.quote(path)
        log("captured", path, "page ready:", self.page_ready)
        if self.page_ready:
            self.emit("shot", {"url": url, "width": self.shot.width, "height": self.shot.height})
        else:
            self._first_url = url

    def _show_now(self):
        log("drawn; showing" if self.pending_show else "drawn, nothing pending")
        if not self.pending_show:
            return
        self.pending_show = False
        self.move(0, 0)
        self.resize(self.shot.width, self.shot.height)
        self.show_all()
        self.fullscreen()
        self.present_with_time(Gtk.get_current_event_time() or Gdk.CURRENT_TIME)
        GLib.timeout_add(80, lambda: (self.get_window() and self.get_window().focus(Gdk.CURRENT_TIME), False)[1])

    # -- commands from the page ---------------------------------------------------------

    def cmd_ready(self, _id):
        self.page_ready = True
        url = getattr(self, "_first_url", None)
        if url and self.shot is not None:
            return {"url": url, "width": self.shot.width, "height": self.shot.height}
        return None

    def cmd_drawn(self, _id):
        """The page has painted the frozen screen: safe to show the window."""
        self._show_now()

    def cmd_read(self, req_id, x, y, w, h):
        """OCR a region (in screen pixels). Answers later, from a thread."""
        shot = self.shot
        if shot is None or w < 4 or h < 4:
            return {"lines": [], "text": "", "findings": []}

        def work():
            started = time.monotonic()
            try:
                region, x0, y0 = engine.crop(shot, x, y, w, h)
                result = engine.recognize(region)
                lines = [{"words": [{"text": wd.text, "x": wd.x + x0, "y": wd.y + y0, "w": wd.w,
                                     "h": wd.h, "conf": wd.conf, "space": wd.space} for wd in line.words],
                          "rtl": False}
                         for line in result.lines]
                text = result.text
                out = {"lines": lines, "text": text, "findings": engine.findings(text),
                       "language": result.language, "ms": int((time.monotonic() - started) * 1000)}
            except (RuntimeError, OSError) as e:
                out = {"error": f"Couldn't read the text: {e}"}
            GLib.idle_add(lambda: (self._resolve(req_id, out), False)[1])
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
        self.shot = None
        return True


LATER = object()


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
