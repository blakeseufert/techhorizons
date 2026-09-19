#!/bin/sh
# The clock panel: the exact time, the date, and a month you can page through.
#
# Redrawing without flicker, without ghosts:
#
# Clearing the screen every second flickers, so we do not. But simply writing
# over the top leaves fragments of the previous frame behind whenever the frame
# gets narrower -- and it always does once, because the window is mapped at one
# size and resized by the compositor a frame later.
#
# So every row is padded to the full width and the whole block is rewritten in
# place each second. Nothing is ever cleared, nothing is ever left over.
SAGE=$(printf '\033[38;2;219;228;198m')
DIM=$(printf '\033[38;2;219;228;198;2m')
CORAL=$(printf '\033[38;2;255;104;70m')
OFF=$(printf '\033[0m')
ROWS=16

# ?1000h turns on mouse reporting: a click arrives as ESC [ M b x y. Students
# click things that look like buttons, and "<  >" looks like buttons.
printf '\033[?25l\033[H\033[2J\033[?1000h'
trap 'printf "\033[?25h\033[?1000l"; stty echo icanon 2>/dev/null' EXIT INT TERM
stty -echo -icanon time 0 min 0 2>/dev/null
ESC=$(printf '\033')

# After an ESC: sets CX/CY (1-based column/row) and returns 0 for a left-button
# press. Anything else -- release, arrow key, stray escape -- returns 1.
click() {
	[ "$(dd bs=1 count=2 2>/dev/null)" = "[M" ] || return 1
	set -- $(dd bs=1 count=3 2>/dev/null | od -An -tu1)
	[ $# -eq 3 ] && [ $(( ($1 - 32) & 3 )) -eq 0 ] || return 1
	CX=$(($2 - 32)); CY=$(($3 - 32))
}

# 0 is this month, -1 last, +1 next.
offset=0

# Print one row, padded to the full width so it erases whatever was there.
line() {
	row="$1"; text="$2"; colour="$3"
	printf '\033[%d;1H%s%s%*s%s' "$row" "$colour" "$text" \
		"$(( cols - ${#text} > 0 ? cols - ${#text} : 0 ))" "" "$OFF"
}

while :; do
	cols=$(stty size 2>/dev/null | cut -d' ' -f2)
	case "$cols" in ''|*[!0-9]*) cols=30 ;; esac
	pad=$(( (cols - 20) / 2 ))
	[ "$pad" -lt 0 ] && pad=0
	indent=$(printf "%${pad}s" "")

	# Resolve the offset to a month and year.
	y=$(date +%Y); m=$(date +%-m)
	m=$((m + offset))
	while [ "$m" -lt 1 ];  do m=$((m + 12)); y=$((y - 1)); done
	while [ "$m" -gt 12 ]; do m=$((m - 12)); y=$((y + 1)); done
	if [ "$offset" -eq 0 ]; then today=$(date +%-d); else today=0; fi

	# Row 1 is never written to, so it has to be wiped explicitly or the
	# pre-resize frame leaves a strip of last month across the top.
	line 1 "" "$OFF"
	line 2 "${indent}$(date '+%H:%M:%S')" "$SAGE"
	line 3 "" "$OFF"
	line 4 "${indent}$(date '+%a %-d %b %Y')" "$DIM"
	line 5 "" "$OFF"

	# Blank the calendar rows FIRST, then draw over them.
	#
	# The obvious order -- draw, then blank whatever the month did not reach --
	# does not work: the read loop runs in a subshell because it is on the end
	# of a pipe, so its row counter never makes it back out here. The parent
	# still thought row was 6 and blanked the whole calendar it had just drawn.
	r=6
	while [ "$r" -lt 15 ]; do line "$r" "" "$OFF"; r=$((r + 1)); done

	row=6
	cal "$m" "$y" 2>/dev/null | while IFS= read -r text; do
		printf '\033[%d;1H%s%s%s%s' "$row" "$indent" "$SAGE" \
			"$(printf '%s' "$text" | sed -E "s/(^| )($today)( |\$)/\1${CORAL}\2${SAGE}\3/")" \
			"$OFF"
		row=$((row + 1))
	done

	line 15 "${indent}<  >  month   t  today" "$DIM"
	r=16
	while [ "$r" -le "$ROWS" ]; do line "$r" "" "$OFF"; r=$((r + 1)); done

	# Poll rather than block, so the seconds keep moving.
	k=$(dd bs=1 count=1 2>/dev/null)
	case "$k" in
		,|'<') offset=$((offset - 1)) ;;
		.|'>') offset=$((offset + 1)) ;;
		t|T)   offset=0 ;;
		q)     exit 0 ;;
		'')    sleep 1 ;;
		"$ESC")
			# row 15 reads "<  >  month   t  today" from column pad+1
			if click && [ "$CY" -eq 15 ]; then
				rel=$((CX - pad))
				if   [ "$rel" -le 2 ];  then offset=$((offset - 1))
				elif [ "$rel" -le 6 ];  then offset=$((offset + 1))
				elif [ "$rel" -ge 13 ]; then offset=0
				fi
			fi ;;
	esac
done
