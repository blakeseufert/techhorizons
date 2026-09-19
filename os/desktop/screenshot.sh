#!/bin/sh
# Capture evidence. Students do this constantly -- it is the single most
# repeated action in the whole course -- so it must be one keypress and must
# never ask where to save.
#
# Local-first by design: the machine has no internet until the Mikrotik stage.
set -eu

EVIDENCE="${TH_EVIDENCE:-$HOME/evidence}"
mkdir -p "$EVIDENCE"
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$EVIDENCE/shot-$STAMP.png"

# A region if they drag one, the whole screen if they just press the key.
if command -v slurp >/dev/null 2>&1 && REGION=$(slurp -d 2>/dev/null); then
	grim -g "$REGION" "$OUT"
else
	grim "$OUT"
fi

# Append to the manifest that th-hub will later sync.
printf '%s\t%s\n' "$STAMP" "$(basename "$OUT")" >> "$EVIDENCE/manifest.tsv"
# Say so. A key that saves a file with no visible sign that it did anything
# gets pressed five more times, and then reported as broken.
hyprctl notify -1 3000 "rgb(FF6846)" "fontsize:18  Screenshot saved to your evidence folder" >/dev/null 2>&1 || true
echo "$OUT"
