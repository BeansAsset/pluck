"""Reads text from a region of the screen, with each word's position.

Uses Tesseract. Settings were picked by measuring on screen-style text
(clean, video-blurred, JPEG-compressed, on coloured backgrounds, light and
dark, 11 to 16 px):

  * enlarge 2x: screen text is small; Tesseract likes ~30 px letters
  * grayscale, and flip light-on-dark to dark-on-light
  * page mode 6 (one block of text): as accurate as automatic layout here,
    and steadier on single lines
  * English only for now; other languages can come later as a setting

No GTK in here, so it can be tested on its own.
"""

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field

from PIL import Image, ImageOps, ImageStat

SCALE = 2


@dataclass
class Word:
    text: str
    conf: float
    x: float          # position and size in the original image's pixels
    y: float
    w: float
    h: float
    space: bool = True   # followed by a space (False when it touches the next piece)


@dataclass
class Line:
    words: list = field(default_factory=list)

    @property
    def text(self):
        out = ""
        for i, w in enumerate(self.words):
            out += w.text
            if i < len(self.words) - 1 and w.space:
                out += " "
        return out

    @property
    def box(self):
        x0 = min(w.x for w in self.words)
        y0 = min(w.y for w in self.words)
        x1 = max(w.x + w.w for w in self.words)
        y1 = max(w.y + w.h for w in self.words)
        return x0, y0, x1 - x0, y1 - y0


@dataclass
class Result:
    lines: list
    language: str

    @property
    def text(self):
        return "\n".join(line.text for line in self.lines)

    @property
    def confidence(self):
        words = [w for line in self.lines for w in line.words]
        return sum(w.conf for w in words) / len(words) if words else 0.0


def prepare(image):
    """Grayscale, 2x, dark text on a light background."""
    gray = ImageOps.grayscale(image)
    gray = gray.resize((gray.width * SCALE, gray.height * SCALE), Image.LANCZOS)
    if ImageStat.Stat(gray).median[0] < 128:
        gray = ImageOps.invert(gray)
    return gray


def _tesseract(prepared, languages, timeout=30):
    with tempfile.TemporaryDirectory(prefix="pluck-") as tmp:
        path = os.path.join(tmp, "region.png")
        prepared.save(path)
        out = subprocess.run(
            ["tesseract", path, "stdout", "-l", languages, "--psm", "6",
             "-c", "preserve_interword_spaces=0", "tsv"],
            capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "Tesseract failed")
    return out.stdout


def parse_tsv(tsv, scale=SCALE):
    """Tesseract's TSV into Lines of Words, back in original pixels."""
    lines = {}
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5":
            continue
        text = cols[11].strip()
        if not text:
            continue
        try:
            block, par, line = int(cols[2]), int(cols[3]), int(cols[4])
            left, top, width, height = (int(c) for c in cols[6:10])
            conf = float(cols[10])
        except ValueError:
            continue
        lines.setdefault((block, par, line), Line()).words.append(
            Word(text, conf, left / scale, top / scale, width / scale, height / scale))
    ordered = [lines[k] for k in sorted(lines)]
    for line in ordered:
        line.words.sort(key=lambda w: w.x)
        join_touching(line.words)
        fix_code_case(line.words)
    return ordered


JOINERS = set("./:-_?=&#%~@+")


def join_touching(words):
    """Tesseract sometimes splits one token in two ("download." + "html").
    When two pieces almost touch and the join involves punctuation, they are
    one token: no space between them."""
    for a, b in zip(words, words[1:]):
        gap = b.x - (a.x + a.w)
        char = (a.w / max(1, len(a.text)) + b.w / max(1, len(b.text))) / 2
        if gap < 0.3 * char and (a.text[-1] in JOINERS or b.text[0] in JOINERS):
            a.space = False


CODE_HINTS = re.compile(r"(^|\s)(sudo|cd|git|apt|pip|npm|curl|wget|ls|cat|echo)(\s|$)|--|[/$=|`]")
# A curved-foot l read as two characters at the start of a word: "1libx264",
# "lLibavcodec", "Ilib", "1Lib".
DOUBLE_L = re.compile(r"^(1l|lL|Il|1L|l1|ll(?=[A-Z]))(?=[a-z])")


def is_monospace(words):
    """True when every letter on the line is the same width, measured from
    the word boxes: a terminal, code, or a monospace font."""
    widths = [w.w / len(w.text) for w in words if len(w.text) >= 3]
    if len(widths) < 3:
        return False
    mean = sum(widths) / len(widths)
    spread = (sum((x - mean) ** 2 for x in widths) / len(widths)) ** 0.5
    return spread / mean < 0.1


def fix_code_case(words):
    """In monospace fonts a lowercase l has a curved foot. Tesseract reads it
    as L ("Libavcodec") or as two characters ("1libx264", "lLibavcodec").
    On monospace or code-looking lines, those become a plain l. Prose in
    ordinary fonts is left alone."""
    line = " ".join(w.text for w in words)
    if not (is_monospace(words) or CODE_HINTS.search(line)):
        return
    for w in words:
        t = DOUBLE_L.sub("l", w.text)
        if len(t) > 1 and t[0] == "L" and t[1:] == t[1:].lower() and any(c.isalpha() for c in t[1:]) \
                and t[1:].replace("-", "").replace("_", "").replace(".", "").isalnum():
            t = "l" + t[1:]
        w.text = t


def recognize(image, languages="eng"):
    """Read the text in a PIL image. Returns a Result."""
    return Result(parse_tsv(_tesseract(prepare(image), languages)), languages)


def crop(screenshot, x, y, w, h, pad=4):
    """A region of the screenshot, padded a little so edge letters survive."""
    x0 = max(0, int(x) - pad)
    y0 = max(0, int(y) - pad)
    x1 = min(screenshot.width, int(x + w) + pad)
    y1 = min(screenshot.height, int(y + h) + pad)
    return screenshot.crop((x0, y0, x1, y1)), x0, y0


# -- things worth acting on --------------------------------------------------

URL = re.compile(r"\b(?:https?://|www\.)[^\s<>\"']+[^\s<>\"'.,;:!?)\]]")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE = re.compile(r"(?<![\w+])\+?\d[\d ()-]{6,}\d\b")


def findings(text):
    """Links, email addresses and phone numbers found in the text."""
    found = []
    seen = set()
    for kind, pattern in (("link", URL), ("email", EMAIL), ("phone", PHONE)):
        for m in pattern.finditer(text):
            value = m.group(0).strip()
            if kind == "phone" and sum(c.isdigit() for c in value) < 7:
                continue
            if kind == "phone" and any(value in f[1] for f in found):
                continue   # digits that are part of a link or address
            if value not in seen:
                seen.add(value)
                found.append((kind, value))
    return found
