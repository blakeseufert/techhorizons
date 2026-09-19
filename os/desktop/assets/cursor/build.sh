#!/bin/sh
# Build the pointer theme from desktop/assets/cursor into $1 (a theme dir).
#
# TWO themes are produced from the one SVG, because two different things draw
# cursors on this desktop:
#
#   hyprcursor  - what Hyprland draws. SVG native, scales to any display.
#   XCursor     - what GTK and Chromium draw for themselves. Bitmaps only, so
#                 the SVG is rendered at four sizes.
#
# Shipping only the first is the obvious mistake: the pointer looks right on
# the wallpaper and then turns back into the stock arrow the moment it crosses
# into a browser window, which is where a student spends nearly all their time.
set -eu

SRC="$(cd -- "$(dirname -- "$0")" && pwd)"
DEST="${1:?usage: build.sh <theme-dir>}"
SVG="$SRC/hyprcursors/default/pointer.svg"
HOTSPOT=0.17

mkdir -p "$DEST"

# --- hyprcursor -------------------------------------------------------
if command -v hyprcursor-util >/dev/null 2>&1; then
	tmp=$(mktemp -d)
	if hyprcursor-util --create "$SRC" -o "$tmp" >/dev/null 2>&1; then
		cp -r "$tmp"/theme_*/. "$DEST/"
	else
		echo "cursor: hyprcursor-util failed; Hyprland will use its built-in arrow" >&2
	fi
	rm -rf "$tmp"
fi

# --- XCursor ----------------------------------------------------------
if command -v rsvg-convert >/dev/null 2>&1 && command -v xcursorgen >/dev/null 2>&1; then
	tmp=$(mktemp -d)
	config="$tmp/pointer.cfg"
	: > "$config"
	for size in 24 32 48 64; do
		rsvg-convert -w "$size" -h "$size" -o "$tmp/$size.png" "$SVG"
		hot=$(awk -v s="$size" -v f="$HOTSPOT" 'BEGIN{printf "%d", s*f}')
		printf '%s %s %s %s\n' "$size" "$hot" "$hot" "$tmp/$size.png" >> "$config"
	done
	mkdir -p "$DEST/cursors"
	xcursorgen "$config" "$DEST/cursors/left_ptr"
	# Every name an app might ask for, pointing at the one we drew.
	for alias in default arrow top_left_arrow; do
		ln -sf left_ptr "$DEST/cursors/$alias"
	done
	rm -rf "$tmp"
else
	echo "cursor: no rsvg-convert/xcursorgen; browser windows keep the stock arrow" >&2
fi

cat > "$DEST/index.theme" <<'THEME'
[Icon Theme]
Name=TechHorizons
Comment=Lucide mouse-pointer-2, in the Tech Horizons palette
THEME
