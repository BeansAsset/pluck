"""Finding QR codes on the frozen screen, and saying what they hold.

Decoding uses ZBar (libzbar), called directly so no Python package is
needed. If the library isn't installed, Pluck works as before, just
without QR codes.
"""

import ctypes
import ctypes.util
import re
import urllib.parse
from dataclasses import dataclass

from PIL import Image, ImageOps

ZBAR_QRCODE = 64
ZBAR_CFG_ENABLE = 0
ZBAR_CFG_TEST_INVERTED = 4      # also find light-on-dark codes (dark mode pages)
Y800 = 0x30303859               # fourcc "Y800": 8-bit grayscale


@dataclass
class Code:
    data: str
    x: int          # bounding box in the image's pixels
    y: int
    w: int
    h: int


_lib = None


def _load():
    global _lib
    if _lib is not None:
        return _lib or None
    name = ctypes.util.find_library("zbar") or "libzbar.so.0"
    try:
        lib = ctypes.CDLL(name)
    except OSError:
        _lib = False
        return None
    p, i, u = ctypes.c_void_p, ctypes.c_int, ctypes.c_uint
    for fn, res, args in (
        ("zbar_image_scanner_create", p, []),
        ("zbar_image_scanner_destroy", None, [p]),
        ("zbar_image_scanner_set_config", i, [p, i, i, i]),
        ("zbar_image_create", p, []),
        ("zbar_image_destroy", None, [p]),
        ("zbar_image_set_format", None, [p, ctypes.c_ulong]),
        ("zbar_image_set_size", None, [p, u, u]),
        ("zbar_image_set_data", None, [p, p, ctypes.c_ulong, p]),
        ("zbar_scan_image", i, [p, p]),
        ("zbar_image_first_symbol", p, [p]),
        ("zbar_symbol_next", p, [p]),
        ("zbar_symbol_get_type", i, [p]),
        ("zbar_symbol_get_data", ctypes.c_char_p, [p]),
        ("zbar_symbol_get_data_length", u, [p]),
        ("zbar_symbol_get_loc_size", u, [p]),
        ("zbar_symbol_get_loc_x", i, [p, u]),
        ("zbar_symbol_get_loc_y", i, [p, u]),
    ):
        f = getattr(lib, fn)
        f.restype, f.argtypes = res, args
    _lib = lib
    return lib


def available():
    return _load() is not None


def _scan(lib, gray):
    scanner = lib.zbar_image_scanner_create()
    image = lib.zbar_image_create()
    try:
        lib.zbar_image_scanner_set_config(scanner, 0, ZBAR_CFG_ENABLE, 0)            # nothing...
        lib.zbar_image_scanner_set_config(scanner, ZBAR_QRCODE, ZBAR_CFG_ENABLE, 1)  # ...but QR codes
        lib.zbar_image_scanner_set_config(scanner, ZBAR_QRCODE, ZBAR_CFG_TEST_INVERTED, 1)
        raw = gray.tobytes()
        buf = ctypes.create_string_buffer(raw, len(raw))
        lib.zbar_image_set_format(image, Y800)
        lib.zbar_image_set_size(image, gray.width, gray.height)
        lib.zbar_image_set_data(image, ctypes.cast(buf, ctypes.c_void_p), len(raw), None)
        found = []
        if lib.zbar_scan_image(scanner, image) > 0:
            sym = lib.zbar_image_first_symbol(image)
            while sym:
                if lib.zbar_symbol_get_type(sym) == ZBAR_QRCODE:
                    n = lib.zbar_symbol_get_data_length(sym)
                    data = ctypes.string_at(lib.zbar_symbol_get_data(sym), n).decode("utf-8", "replace")
                    pts = [(lib.zbar_symbol_get_loc_x(sym, k), lib.zbar_symbol_get_loc_y(sym, k))
                           for k in range(lib.zbar_symbol_get_loc_size(sym))]
                    if pts:
                        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                        found.append(Code(data, min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1))
                sym = lib.zbar_symbol_next(sym)
        return found
    finally:
        lib.zbar_image_destroy(image)
        lib.zbar_image_scanner_destroy(scanner)


def find(image):
    """Every QR code in a PIL image. Small codes (a video in a corner) are
    also looked for at twice the size."""
    lib = _load()
    if lib is None:
        return []
    gray = image.convert("L")
    codes = _scan(lib, gray)
    if not codes and gray.width * gray.height <= 4000 * 2500:
        big = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
        codes = [Code(c.data, c.x // 2, c.y // 2, c.w // 2, c.h // 2) for c in _scan(lib, big)]
    if not codes:
        # Some screens show codes light on dark and ZBar misses them at times.
        codes = _scan(lib, ImageOps.invert(gray))
    seen, out = set(), []
    for c in codes:
        if c.data not in seen:
            seen.add(c.data)
            out.append(c)
    return out


# -- what a code holds ----------------------------------------------------------------

# Second-level names that sit under a country's domain, like example.co.uk.
_SHARED = {"co", "com", "org", "net", "gov", "ac", "edu", "or", "ne", "go"}


def site_of(host):
    """The part of a host name that says whose site it is: the registrable
    domain. paypal.com.secure-login.xyz -> secure-login.xyz."""
    labels = [l for l in host.lower().split(".") if l]
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SHARED:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _wifi(data):
    fields = dict(re.findall(r"([STPH]):((?:\\.|[^;])*);", data[5:]))
    unescape = lambda v: re.sub(r"\\(.)", r"\1", v)
    return {"kind": "wifi", "network": unescape(fields.get("S", "")),
            "password": unescape(fields.get("P", "")), "security": fields.get("T", "")}


def describe(data):
    """What the page needs to show and offer for a code's contents."""
    text = data.strip()
    lower = text.lower()
    if lower.startswith(("http://", "https://")):
        parts = urllib.parse.urlsplit(text)
        host = parts.hostname or ""
        return {"kind": "link", "url": text, "host": host, "site": site_of(host),
                "secure": parts.scheme == "https",
                # Look-alike letters are hidden in punycode (xn--); say so.
                "unusual": "xn--" in host or any(ord(ch) > 127 for ch in host)}
    if lower.startswith("wifi:"):
        return _wifi(text)
    if lower.startswith("mailto:"):
        return {"kind": "email", "value": text[7:].split("?")[0]}
    if lower.startswith("tel:"):
        return {"kind": "phone", "value": text[4:]}
    return {"kind": "text", "value": text}
