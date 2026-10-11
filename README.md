# Pluck

Copy text from anything on your screen: a paused video, a screenshot, a
photo, a game, a PDF that's really an image. And open the QR codes on it,
without reaching for your phone.

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
- **Click a QR code** to see where it goes, then open it or copy it
- **Search** the web for it
- **Show text** to check what was read, and **Edit** to fix it before copying

Everything runs on your computer. Nothing is sent anywhere unless you press
Search or open a link.

## Scan QR codes on your screen

A QR code in a video, a slide, a PDF or a web page, and your phone is across
the room? Press **Super+Shift+T**: every QR code on the screen gets an
outline. Click one to see what's inside.

![A QR code at the end of a recorded talk: Pluck outlines it, and clicking it shows the link with Open and Copy link](docs/qr.gif)

- **Links** show the whole address before anything opens, with the site it
  really goes to in bold, so `paypal.com.secure-login.xyz` can't pass for
  PayPal. Plain `http://` and look-alike letters in the address are
  pointed out.
- **Wi-Fi codes** (the ones on routers and café tables) give you the
  network's name and a button to copy its password.
- **Email addresses, phone numbers and plain text** can be copied, and
  emails opened in your mail app.

It finds codes that are small (a video in a corner of the screen), light on
dark, or several at once, and works on X11 and Wayland like the rest of
Pluck. Decoding uses [ZBar](https://github.com/mchehab/zbar) and happens on
your computer; nothing is opened until you choose to.

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
| Linux Mint, Ubuntu, Debian, Pop!_OS | `sudo apt install tesseract-ocr python3-gi python3-pil gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libzbar0` |
| Fedora | `sudo dnf install tesseract tesseract-langpack-eng python3-gobject python3-pillow gtk3 webkit2gtk4.1 zbar-libs` |
| Arch, Manjaro | `sudo pacman -S --needed tesseract tesseract-data-eng python-gobject python-pillow gtk3 webkit2gtk-4.1 zbar` |
| openSUSE | `sudo zypper install tesseract-ocr tesseract-ocr-traineddata-english python3-gobject python3-Pillow typelib-1_0-Gtk-3_0 typelib-1_0-WebKit2-4_1 libzbar0` |

The last package in each line, ZBar, is only for QR codes. Many systems
already have it; without it Pluck works as usual and the setup script tells
you how to add it.

The setup script adds Pluck to your apps menu, starts it quietly at login so
the shortcut responds instantly, and sets **Super+Shift+T** (Super is the
Windows key) on Cinnamon, GNOME, Budgie, MATE, Xfce and KDE. On other
desktops it tells you what to bind. `install-integration.sh --remove` undoes
all of it.

Works on X11 and Wayland. On X11 Pluck reads the screen directly; on Wayland
it uses the desktop's screenshot portal, and some desktops ask once whether
Pluck may take screenshots. It freezes the monitor your pointer is on, and
handles HiDPI and fractional scaling.

Tested on Linux Mint 22 (Cinnamon, X11), including the portal route and QR
codes. Other
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
`qr.py` looks for QR codes on the whole frozen screen at the same time, using
the ZBar library directly, and describes what each one holds. Pluck stays
running between uses: the shortcut responds instantly, and copied
text stays on the clipboard after the overlay closes.

```
pluck/
  engine.py      OCR: prepare, recognise, positions, fixes, links and numbers
  qr.py          QR codes: finding them, and what's in them (links, Wi-Fi, text)
  capture.py     the screenshot: X11 directly, or the portal on Wayland
  main.py        the app: the full-screen overlay, clipboard, actions
  web/           the overlay (HTML, CSS, JS, Inter font)
tools/
  integrate.py   setup for any common distro and desktop
tests/           python3 -m unittest discover -s tests
```

## License

GPL-3.0-or-later (`LICENSE`). Inter is under the SIL Open Font License 1.1.
