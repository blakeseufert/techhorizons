#!/bin/sh
# "Update Available" pill.
#
# Course content is the thing that actually updates for a student, so this
# asks the course repo whether the checkout is behind its remote. No network,
# no repo, or no upstream all mean "nothing to say" -- the pill goes quiet
# rather than showing a false alarm.
set -u
COURSE_DIR="${TH_COURSE_DIR:-/opt/techhorizons/course}"

# Print NOTHING when there is nothing to say. waybar hides a custom module
# whose exec produces no text, so the pill disappears entirely rather than
# sitting there saying "up to date" -- which is only worth screen space on the
# rare day it is untrue.
quiet() { printf '\n'; exit 0; }

[ -d "$COURSE_DIR/.git" ] || quiet
command -v git >/dev/null 2>&1 || quiet

# Never block the bar on a slow network.
timeout 20 git -C "$COURSE_DIR" fetch --quiet 2>/dev/null || quiet

behind=$(git -C "$COURSE_DIR" rev-list --count HEAD..@{upstream} 2>/dev/null || echo 0)
[ "${behind:-0}" -gt 0 ] 2>/dev/null || quiet

printf '{"text":"Update Available","tooltip":"%s new course update(s). Click to open."}\n' "$behind"
