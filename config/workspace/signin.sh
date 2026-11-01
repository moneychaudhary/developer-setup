#!/bin/bash
# Rebuild the daily workspace from plain windows: Orca full screen, three splits, Docker and LocalStack.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
DIR="$HOME/.local/share/workspace"
MOUSE="$DIR/mouse"
YTM="$HOME/Applications/Chrome Apps.localized/YouTube Music.app"
# Chrome profile folder for the work profile; override with WORKSPACE_CHROME_PROFILE
CHROME_PROFILE="${WORKSPACE_CHROME_PROFILE:-Profile 1}"
log() { echo "$(date '+%H:%M:%S') $*"; }

# Start Docker hidden, then LocalStack once the Docker engine answers.
start_backend() {
  log "docker: starting"
  open -g -a Docker
  for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || { log "docker: not ready after 3 minutes"; return; }
  log "docker: ready"
  # Close the Docker Desktop dashboard if it opened; the engine keeps running
  osascript -e 'tell application "System Events" to tell process "Docker Desktop" to repeat with w in windows
    click (first button of w whose subrole is "AXCloseButton")
  end repeat' >/dev/null 2>&1 && log "docker: dashboard closed"
  if lstk status >/dev/null 2>&1; then log "localstack: already running"; return; fi
  log "localstack: starting"
  if lstk start --type aws --timeout 5m </dev/null; then log "localstack: ready"; else log "localstack: failed to start"; fi
}

# Run a System Events command against a process; prints nothing on failure.
se() { osascript -e "tell application \"System Events\" to tell process \"$1\" to $2" 2>/dev/null; }

# Wait until a process has a window System Events can see.
wait_window() { for _ in $(seq 1 30); do [ "$(se "$1" "count windows")" -ge 1 ] 2>/dev/null && return 0; sleep 0.5; done; return 1; }

# Bring an app forward (switching to its desktop) without sending it Apple events (args: open-target process).
front() {
  for _ in 1 2 3 4 5; do
    open "$1"; sleep 1.2
    if [ "$(osascript -e 'tell application "System Events" to get name of first process whose frontmost is true')" = "$2" ]; then
      # Web-app shims expose no windows to System Events, so only wait for real apps
      [ "$2" = app_mode_loader ] || wait_window "$2"
      sleep 1
      return 0
    fi
  done
  return 1
}

# Main window full-screen state of the front process (call after front).
main_fullscreen() { se "$1" 'get value of attribute "AXFullScreen" of (first window whose value of attribute "AXMain" is true)'; }

# Bring an app forward and leave full screen (or a split) so it becomes a plain window (args: open-target process).
plain() {
  front "$1" "$2" || return 1
  if [ "$2" = app_mode_loader ]; then
    se app_mode_loader 'click menu item "Exit Full Screen" of menu "View" of menu bar 1' >/dev/null && sleep 2.5
  elif [ "$(main_fullscreen "$2")" = "true" ]; then
    se "$2" 'set value of attribute "AXFullScreen" of (first window whose value of attribute "AXMain" is true) to false' >/dev/null
    sleep 2.5
  fi
  return 0
}

# Click Window > Full Screen Tile > SIDE of Screen (call after front).
tile() { se "$1" "click menu item \"$2 of Screen\" of menu 1 of menu item \"Full Screen Tile\" of menu \"Window\" of menu bar 1" >/dev/null; }

# Close a pending Split View picker so a failed step does not block the next one.
cancel_picker() { osascript -e 'tell application "System Events" to key code 53' >/dev/null 2>&1; sleep 1.5; }

# Click the partner window in the Split View picker, then push the divider right (args: partner-owner partner-side left-owner).
finish_split() {
  local pick="" left="" x y w h sw sh
  # Wait for the picker animation to settle: the same position twice in a row
  local prev=""
  sleep 1.5
  for _ in $(seq 1 20); do
    pick=$("$MOUSE" find "$1" "$2")
    [ -n "$pick" ] && [ "$pick" = "$prev" ] && break
    prev="$pick"; pick=""; sleep 0.4
  done
  [ -n "$pick" ] || { log "split: $1 not offered in picker (last seen: $prev)"; [ -n "$DEBUG_SHOTS" ] && screencapture -x "$DEBUG_SHOTS/fail-$1.png"; cancel_picker; return 1; }
  read -r x y w h <<<"$pick"
  "$MOUSE" click $((x + w / 2)) $((y + h / 3)); sleep 3
  for _ in $(seq 1 10); do left=$("$MOUSE" find "$3" left) && break; sleep 0.5; done
  [ -n "$left" ] || { log "split: $3 not on the left after pairing"; return 1; }
  read -r x y w h <<<"$left"
  read -r sw sh <<<"$("$MOUSE" screen)"
  # A split window starts at the left edge, is narrower than the screen and reaches its bottom
  if [ "$x" -gt 5 ] || [ "$w" -gt $((sw - 50)) ] || [ $((y + h)) -lt $((sh - 8)) ]; then
    log "split: $3 did not enter the split"; [ -n "$DEBUG_SHOTS" ] && screencapture -x "$DEBUG_SHOTS/nosplit-$3.png"; return 1
  fi
  "$MOUSE" drag $((x + w + 4)) $((sh / 2)) $((sw - 10)) $((sh / 2)); sleep 1.5
}

# Pair LEFT and RIGHT on one full-screen desktop with RIGHT at its minimum width, retrying once (args: left-app left-process right-app right-process).
split_pair() {
  local try
  for try in 1 2; do
    if front "/Applications/$1.app" "$2" && sleep 1 && tile "$2" Left && finish_split "$4" right "$2"; then
      log "split: $2 | $4 done"; return 0
    fi
    log "split: $2 | $4 attempt $try failed"
    cancel_picker
    plain "/Applications/$1.app" "$2"; plain "/Applications/$3.app" "$4"
  done
}

# Sourcing with --lib loads the functions without running anything
[ "${1:-}" = --lib ] && return 0

start_backend &

# Start the menu bar tools in the background
open -g -a Stats

# Close Granola's window once it appears; the app keeps running in the menu bar to catch meetings
close_granola() {
  open -g -j -a Granola
  for _ in $(seq 1 30); do
    if [ "$(se Granola "count windows")" -ge 1 ] 2>/dev/null; then
      sleep 1
      se Granola 'repeat with w in windows
        click (first button of w whose subrole is "AXCloseButton")
      end repeat' >/dev/null && log "granola: window closed"
      return
    fi
    sleep 1
  done
  log "granola: running without a window"
}
close_granola &

# Open everything as plain windows first.
log "layout: resetting windows"
plain /Applications/Slack.app Slack
plain /Applications/Claude.app Claude
plain "/Applications/Visual Studio Code.app" Code
plain /Applications/ChatGPT.app ChatGPT
# Start Chrome on the work profile, and add a window if it is running without one
pgrep -xq "Google Chrome" || { open -na "Google Chrome" --args --profile-directory="$CHROME_PROFILE"; sleep 3; }
plain "/Applications/Google Chrome.app" "Google Chrome"
[ "$(se "Google Chrome" "count windows")" -ge 1 ] 2>/dev/null || { open -na "Google Chrome" --args --profile-directory="$CHROME_PROFILE"; sleep 3; }
open "$YTM"; sleep 3
plain "$YTM" app_mode_loader

log "orca: full screen"
if front /Applications/Orca.app Orca && [ "$(main_fullscreen Orca)" != "true" ]; then
  se Orca 'set value of attribute "AXFullScreen" of (first window whose value of attribute "AXMain" is true) to true' >/dev/null; sleep 2.5
fi

split_pair Slack Slack Claude Claude
split_pair "Visual Studio Code" Code ChatGPT ChatGPT

# Chrome's own windows hide each other in the picker, so tile YouTube Music right and pick Chrome.
if front "$YTM" app_mode_loader && tile app_mode_loader Right; then
  finish_split "Google Chrome" left "Google Chrome" && log "split: Google Chrome | YouTube Music done"
else
  log "split: could not tile YouTube Music"
fi

wait
log "signin finished"
