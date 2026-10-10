# Pluck

Copy text from anything on your screen: a paused video, a screenshot, a
photo, a game, a PDF that's really an image.

![Pluck reading a command from a paused tutorial video](docs/screenshot.png)

Select part of it with the mouse, right on the original:

![Part of a line selected with the mouse, highlighted on the original text](docs/select.png)

Check and fix what was read before copying:

![The edit box with the recognised command](docs/edit.png)

Press **Super+Shift+T**. The screen freezes (so moving video holds still) and
dims; drag over what you want. Pluck reads it and lays the text invisibly over
the original pixels, so you can select part of it with the mouse, or:

- **Copy text** (or press Enter or Ctrl+C), and Pluck closes
- **Open** a link it found, **Email** an address, **Copy** a phone number
- **Search** the web for it
- **Show text** to check what was read, and **Edit** to fix it before copying
- **Vertorama**: capture the whole of a scrolling area, not just what fits

## Vertorama

For a chat, a long web page or a document that doesn't fit on screen: select
the scrolling area and press **Vertorama**. Pluck scrolls it for you, a step
at a time, and joins the steps into one tall image. It stops by itself at the
end; move the mouse to stop sooner and keep what it has so far.

When it's done you can **Save image** (PNG) or **Save PDF** (split into pages
between lines of text, with the text searchable and selectable), both into
Pictures › Vertorama, or **Copy image** and **Copy text**.

Bars that stay put while the rest scrolls, like a chat's title bar and message
box, appear once, at the top and bottom. Joins are found by matching the
pixels of each step against the last one, so a blinking cursor or an animated
picture doesn't throw it off. If two steps can't be matched it goes back and
takes smaller ones, and if they still can't be, it stops there instead of
guessing.

Vertorama needs X11 for now: Wayland doesn't let one app scroll another's
window. Scrolling it yourself on Wayland is planned.

Everything runs on your computer. Nothing is sent anywhere unless you press
Search or open a link.

## Install

Get the code, then run the setup script. It checks what Pluck needs and, if
anything is missing, shows the exact command for your distro:

```sh
git clone https://github.com/BeansAsset/pluck.git ~/pluck
~/pluck/install-integration.sh
```

What it needs, if you'd rather install it first:

| Distro | Command |
| --- | --- |
| Linux Mint, Ubuntu, Debian, Pop!_OS | `sudo apt install tesseract-ocr python3-gi python3-pil gir1.2-gtk-3.0 gir1.2-webkit2-4.1 python3-xlib` |
| Fedora | `sudo dnf install tesseract tesseract-langpack-eng python3-gobject python3-pillow gtk3 webkit2gtk4.1 python3-xlib` |
| Arch, Manjaro | `sudo pacman -S --needed tesseract tesseract-data-eng python-gobject python-pillow gtk3 webkit2gtk-4.1 python-xlib` |
| openSUSE | `sudo zypper install tesseract-ocr tesseract-ocr-traineddata-english python3-gobject python3-Pillow typelib-1_0-Gtk-3_0 typelib-1_0-WebKit2-4_1 python3-python-xlib` |

The setup script adds Pluck to your apps menu, starts it quietly at login so
the shortcut responds instantly, and sets **Super+Shift+T** (Super is the
Windows key) on Cinnamon, GNOME, Budgie, MATE, Xfce and KDE. On other
desktops it tells you what to bind. (python-xlib is only for Vertorama on
X11.) `install-integration.sh --remove` undoes
all of it.

Works on X11 and Wayland. On X11 Pluck reads the screen directly; on Wayland
it uses the desktop's screenshot portal, and some desktops ask once whether
Pluck may take screenshots. It freezes the monitor your pointer is on, and
handles HiDPI and fractional scaling.

Tested on Linux Mint 22 (Cinnamon, X11), including the portal route. Other
desktops and distros are covered by the setup script's tests but not yet by
hand; reports are welcome. Reads English for now.

## Run it by hand

```sh
./pluck-app                  # freeze the screen and select
./pluck-app --background     # start quietly, ready for the shortcut
```

## How well it reads

Measured on screen-style text at 11 to 16 px, light and dark:

| Text | Accuracy |
| --- | --- |
| Clean screen text | 99.7% |
| Blurred, like a paused video | 99.5% |
| Heavily compressed (JPEG) | 99.4% |
| On a coloured background | 99.7% |

Two fixes for things that went wrong on real screens:

- In monospace fonts a lowercase `l` has a curved foot and was read as `L`
  (`Libavcodec`). On lines that look like code, Pluck fixes a leading `L` in
  an otherwise lowercase word. Normal sentences are left alone.
- Tesseract sometimes splits one token in two (`download. html`). Pieces that
  touch, joined by punctuation, are put back together.

Known limits: a lone `l` can come out as `|`, and very small or stylised text
(game fonts, logos) reads worse. Show text and Edit are there for that.

## How it works

`capture.py` takes the screenshot and cuts it to the monitor you're on.
`engine.py` crops the selected area from the frozen screen, enlarges it 2x,
turns it into dark-on-light grayscale and runs Tesseract, which returns each
word with its position. The page (`web/`) places a transparent copy of every
word exactly over the original, which is what makes mouse selection line up.
Pluck stays running between uses: the shortcut responds instantly, and copied
text stays on the clipboard after the overlay closes.

```
pluck/
  engine.py      OCR: prepare, recognise, positions, fixes, links and numbers
  capture.py     the screenshot: X11 directly, or the portal on Wayland
  main.py        the app: the full-screen overlay, clipboard, actions
  bridge.py      a window holding one of the web pages, and how they talk
  vertorama.py   scrolling and capturing, PDF pages, text of a tall image
  stitch.py      joining the steps: finding each shift, fixed bars
  web/           the overlay and the Vertorama window (HTML, CSS, JS, Inter font)
tools/
  integrate.py   setup for any common distro and desktop
tests/           python3 -m unittest discover -s tests
```

## License

GPL-3.0-or-later (`LICENSE`). Inter is under the SIL Open Font License 1.1.
