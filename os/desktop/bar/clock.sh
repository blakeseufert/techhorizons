#!/bin/sh
# Dock clock: short enough to glance at. The date, the seconds and the month
# live in the panel behind it -- panel/clock.sh.
printf '{"text":"%s","tooltip":""}\n' "$(date '+%a  %H:%M')"
