#!/bin/sh
# Paint the desktop background.
#
# swaybg because it is packaged for Alpine and does exactly one thing;
# hyprpaper and swww are not in any Alpine repo.
#
# TH_WALLPAPER overrides the image. The shipped alternate is
# wallpaper-ziggurat.jpg -- same series, different structure.
set -u
WALL="${TH_WALLPAPER:-/opt/techhorizons/desktop/assets/wallpaper-fieldnode.jpg}"
[ -f "$WALL" ] || WALL=/opt/techhorizons/desktop/assets/wallpaper-ziggurat.jpg
[ -f "$WALL" ] || exit 0

pkill -x swaybg 2>/dev/null
# --mode fill: cover the output and crop, never letterbox or stretch.
exec swaybg --image "$WALL" --mode fill --color 282A29
