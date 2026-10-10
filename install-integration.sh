#!/bin/sh
# Sets up Pluck for your user (no sudo):
#   - Pluck in your apps menu, with its icon
#   - Pluck starts quietly at login, so the shortcut responds instantly
#   - Super+Shift+T opens Pluck (a Cinnamon custom shortcut)
#
#   ./install-integration.sh            set it all up
#   ./install-integration.sh --remove   undo all of it
set -e
here=$(cd "$(dirname "$0")" && pwd)
apps="$HOME/.local/share/applications/io.github.beansasset.Pluck.desktop"
autostart="$HOME/.config/autostart/io.github.beansasset.Pluck.desktop"
icon="$HOME/.local/share/icons/hicolor/scalable/apps/io.github.beansasset.Pluck.svg"
key_path="/org/cinnamon/desktop/keybindings/custom-keybindings/pluck/"
key_schema="org.cinnamon.desktop.keybindings.custom-keybinding:$key_path"
binding="<Super><Shift>t"

# Add or remove "pluck" in Cinnamon's list of custom shortcuts.
custom_list() {
  python3 - "$1" <<'PY'
import ast, subprocess, sys
raw = subprocess.run(["gsettings", "get", "org.cinnamon.desktop.keybindings", "custom-list"],
                     capture_output=True, text=True).stdout.strip()
items = ast.literal_eval(raw.replace("@as ", "")) if raw else []
if sys.argv[1] == "add" and "pluck" not in items:
    items.append("pluck")
elif sys.argv[1] == "remove":
    items = [i for i in items if i != "pluck"]
else:
    sys.exit(0)
subprocess.run(["gsettings", "set", "org.cinnamon.desktop.keybindings", "custom-list", str(items)], check=True)
PY
}

if [ "$1" = "--remove" ]; then
  rm -f "$apps" "$autostart" "$icon"
  if command -v gsettings >/dev/null && gsettings list-schemas | grep -q org.cinnamon.desktop.keybindings; then
    custom_list remove
    gsettings reset-recursively "$key_schema" 2>/dev/null || true
  fi
  echo "Removed Pluck's menu entry, login item and shortcut."
  exit 0
fi

mkdir -p "$(dirname "$apps")" "$(dirname "$autostart")" "$(dirname "$icon")"
cp "$here/data/io.github.beansasset.Pluck.svg" "$icon"

cat > "$apps" <<EOF
[Desktop Entry]
Type=Application
Name=Pluck
Comment=Copy text from anything on your screen
Exec=$here/pluck-app
Icon=io.github.beansasset.Pluck
Categories=Utility;
Keywords=ocr;text;copy;screen;screenshot;lens;extract;
StartupNotify=false
EOF

cat > "$autostart" <<EOF
[Desktop Entry]
Type=Application
Name=Pluck
Comment=Ready for Super+Shift+T
Exec=$here/pluck-app --background
Icon=io.github.beansasset.Pluck
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF
echo "Added Pluck to your apps menu, and set it to start quietly at login."

if command -v gsettings >/dev/null && gsettings list-schemas | grep -q org.cinnamon.desktop.keybindings; then
  gsettings set "$key_schema" name "Pluck"
  gsettings set "$key_schema" command "$here/pluck-app"
  gsettings set "$key_schema" binding "['$binding']"
  custom_list add
  echo "Super+Shift+T now opens Pluck. Change it in System Settings > Keyboard > Shortcuts > Custom Shortcuts."
else
  echo "Not on Cinnamon: add a shortcut for $here/pluck-app in your desktop's keyboard settings."
fi

# Start it now so the shortcut works straight away.
"$here/pluck-app" --background >/dev/null 2>&1 &
