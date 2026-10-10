#!/bin/sh
# Sets Pluck up for your user, on any common desktop (no sudo):
#   - checks what Pluck needs, and shows the install command if anything's missing
#   - Pluck in your apps menu, with its icon
#   - Pluck starts quietly at login, so the shortcut responds instantly
#   - Super+Shift+T opens Pluck (Cinnamon, GNOME, Budgie, MATE, Xfce, KDE)
#
#   ./install-integration.sh            set it all up
#   ./install-integration.sh --remove   undo all of it
here=$(cd "$(dirname "$0")" && pwd)
if [ "$1" = "--remove" ]; then
  exec python3 "$here/tools/integrate.py" remove
fi
exec python3 "$here/tools/integrate.py" install
