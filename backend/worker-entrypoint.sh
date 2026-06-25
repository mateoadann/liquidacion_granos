#!/bin/sh
# Worker entrypoint: runs the RQ worker under a virtual X display.
#
# Why not xvfb-run: xvfb-run launches the worker as a *child* and keeps
# running itself. When the worker process dies (e.g. a Playwright/chromium
# crash), xvfb-run can stay alive holding the Xvfb server, so the container
# stays "Up" with no worker inside — restart never triggers. By starting Xvfb
# ourselves and `exec`-ing the worker, the Python process becomes PID 1: if it
# dies the container dies and `restart: unless-stopped` brings it back.
set -e

DISPLAY_NUM="${XVFB_DISPLAY:-99}"
SCREEN="${XVFB_SCREEN:-1366x768x24}"

Xvfb ":${DISPLAY_NUM}" -screen 0 "${SCREEN}" -nolisten tcp &
XVFB_PID=$!

# If Xvfb dies, take the container down too so it gets restarted.
trap 'kill "${XVFB_PID}" 2>/dev/null' TERM INT

export DISPLAY=":${DISPLAY_NUM}"

# Give Xvfb a moment to come up before launching the worker.
# ponytail: fixed sleep instead of polling with xdpyinfo (would need x11-utils);
# Xvfb is ready in <1s. If chromium ever races the display, switch to a poll.
sleep 1

exec python -u worker.py
