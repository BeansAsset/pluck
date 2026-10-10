"""Vertorama's stitching: turns frames of a scrolling area into one tall image.

Each new frame is matched against the previous one to find how far the
content moved:

  1. Every row of pixels gets a fingerprint: the row shrunk to a few dozen
     values and rounded, so tiny rendering differences don't matter.
  2. Rows that are common within a frame (blank space, repeated lines) say
     nothing about position and are ignored. Every other row looks up where
     the same fingerprint was in the previous frame, and votes for that
     shift. A blinking cursor or an animated picture only costs a few votes.
  3. The winning shifts are checked by comparing the actual pixels of the
     overlap, and the one that matches best is kept.

Rows that stay put while the rest moves, like a chat's title bar or its
message box, are a fixed header and footer: they're kept once, at the top
and bottom, and only the moving part in between is stitched.

New strips are cut a little above the bottom of the moving part, because
many apps draw a shadow or a "more below" line there while scrolling. The
last frame supplies those final rows once, at the very end.

Pure Python and Pillow, no numpy, so there's nothing extra to install.
"""

from collections import Counter

from PIL import Image, ImageChops

SIG_WIDTH = 32          # values per row fingerprint
MIN_VOTES = 6           # rows that must agree on a shift
ROW_SAME = 4.0          # a row whose mean pixel difference is below this counts as matching (0-255)
MIN_MATCHING = 0.6      # share of overlapping rows that must match for a shift to be trusted
EDGE = 12               # rows next to the footer that new strips are not taken from


def fingerprints(image):
    """One hashable fingerprint per row of a frame."""
    gray = image.convert("L")
    small = gray.resize((SIG_WIDTH, gray.height), Image.BOX)
    data = small.tobytes()
    return [bytes(v >> 3 for v in data[i * SIG_WIDTH:(i + 1) * SIG_WIDTH]) for i in range(gray.height)]


def row_differences(a, b):
    """Mean pixel difference of each row between two same-size images."""
    diff = ImageChops.difference(a.convert("L"), b.convert("L"))
    return list(diff.resize((1, diff.height), Image.BOX).tobytes())


def fixed_edges(prev, cur, limit):
    """How many rows at the top and bottom stayed put between two frames.
    Rows count as unchanged when they're nearly identical, so a blinking
    cursor in a message box doesn't cut the footer short."""
    rows = row_differences(prev, cur)
    top = 0
    while top < limit and rows[top] < ROW_SAME:
        top += 1
    bottom = 0
    while bottom < limit and rows[len(rows) - 1 - bottom] < ROW_SAME:
        bottom += 1
    return top, bottom


def _mismatch(prev, cur, top, bottom, shift):
    """Share of rows that don't match when prev's band is moved up by shift.
    Judged row by row, so a small animated area only spoils its own rows."""
    height = prev.height - top - bottom - shift
    if height <= 0:
        return 1.0
    a = prev.crop((0, top + shift, prev.width, top + shift + height))
    b = cur.crop((0, top, cur.width, top + height))
    rows = row_differences(a, b)
    return sum(1 for r in rows if r >= ROW_SAME) / len(rows)


def find_shift(prev, cur, prev_sig, cur_sig, top=0, bottom=0):
    """How many pixels the content moved up from prev to cur, inside the band
    between a fixed header (top rows) and footer (bottom rows).

    Returns (shift, mismatch); shift is None when no reliable match was
    found. A shift of 0 means nothing moved.
    """
    end = len(cur_sig) - bottom
    band_prev = prev_sig[top:end]
    band_cur = cur_sig[top:end]
    if not band_prev:
        return None, 255.0
    if band_prev == band_cur:
        return 0, 0.0
    if _mismatch(prev, cur, top, bottom, 0) <= 1 - MIN_MATCHING:
        return 0, 0.0    # only something small changed in place (a cursor, a GIF)

    common_prev = Counter(band_prev)
    common_cur = Counter(band_cur)
    where = {sig: i for i, sig in enumerate(band_prev) if common_prev[sig] == 1}
    votes = Counter()
    for j, sig in enumerate(band_cur):
        if common_cur[sig] != 1:
            continue
        i = where.get(sig)
        if i is not None and i > j:
            votes[i - j] += 1

    best_shift, best_error = None, 1.0
    for shift, count in votes.most_common(4):
        if count < MIN_VOTES:
            break
        error = _mismatch(prev, cur, top, bottom, shift)
        if error < best_error:
            best_shift, best_error = shift, error
    if best_shift is None or best_error > 1 - MIN_MATCHING:
        return None, best_error
    return best_shift, best_error


class Stitcher:
    """Feed frames of the same area in scroll order; get one tall image."""

    def __init__(self, max_height=60000):
        self.max_height = max_height
        self.first = None
        self.last = None
        self.last_sig = None
        self.header = 0
        self.footer = 0
        self.edges_known = False
        self.pieces = []        # moving-band strips, top to bottom
        self.cut = 0            # band row in the last frame where the pieces end
        self.height = 0

    def add(self, frame):
        """Add the next frame. Returns the shift found: 0 when nothing moved
        (the end was reached), None when it couldn't be matched."""
        frame = frame.convert("RGB")
        sig = fingerprints(frame)
        if self.first is None:
            self.first = self.last = frame
            self.last_sig = sig
            self.height = frame.height
            return None if frame.height == 0 else -1

        if frame.size != self.last.size:
            return None
        if not self.edges_known:
            limit = frame.height // 3
            top, bottom = fixed_edges(self.last, frame, limit)
            if top + bottom >= frame.height:     # identical frames: no motion yet
                return 0
            self.header, self.footer = top, bottom

        shift, _error = find_shift(self.last, frame, self.last_sig, sig, self.header, self.footer)
        if shift is None:
            return None
        if shift == 0:
            return 0
        band = frame.height - self.header - self.footer
        edge = min(EDGE, band // 4)
        if not self.edges_known:
            self.edges_known = True
            self.cut = band - edge
            self.pieces.append(self.first.crop((0, self.header, frame.width, self.header + self.cut)))
        start = self.cut - shift          # where the new content begins in this frame's band
        if start < 0:
            return None                   # moved too far to cut clear of the edge
        self.cut = band - edge
        if self.cut > start:
            self.pieces.append(frame.crop((0, self.header + start, frame.width, self.header + self.cut)))
        else:
            self.cut = start
        self.height += shift
        self.last, self.last_sig = frame, sig
        return shift

    @property
    def full(self):
        return self.height >= self.max_height

    def result(self):
        """The tall image: header once, every moving strip, footer once."""
        if self.first is None:
            return None
        if not self.pieces:
            return self.first.copy()
        w, h = self.first.size
        header = self.first.crop((0, 0, w, self.header))
        tail = self.last.crop((0, self.header + self.cut, w, h - self.footer))
        footer = self.last.crop((0, h - self.footer, w, h))
        total = header.height + sum(p.height for p in self.pieces) + tail.height + footer.height
        out = Image.new("RGB", (w, total))
        y = 0
        for part in (header, *self.pieces, tail, footer):
            out.paste(part, (0, y))
            y += part.height
        return out
