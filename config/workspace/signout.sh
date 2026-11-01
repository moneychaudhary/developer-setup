#!/bin/bash
# Stop LocalStack, quit every open app through its own Quit menu, then shut down with nothing left to restore.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
log() { echo "$(date '+%H:%M:%S') $*"; }

# Every app with a Dock icon except Finder and the two workspace shortcuts.
apps() {
  osascript -e 'tell application "System Events" to get name of every process whose background only is false' 2>/dev/null \
    | tr ',' '\n' | sed 's/^ *//' | grep -vxE 'Finder|SignIn|SignOut|applet' | grep -v '^$'
}

# Send a signal to an app using the process ID System Events reports.
signal_app() {
  local pid
  pid=$(osascript -e "tell application \"System Events\" to get unix id of process \"$2\"" 2>/dev/null)
  [ -n "$pid" ] && kill "-$1" "$pid" 2>/dev/null
}

# Dry run lists what would happen and changes nothing.
if [ "$1" = "--dry-run" ]; then log "dry run: would stop LocalStack, quit: $(apps | paste -sd, -)"; log "dry run: would shut down"; exit 0; fi

# Detach so the SignOut app can exit first and is not reopened at the next login.
if [ "$1" != "--detached" ]; then
  nohup "$0" --detached >>"$HOME/Library/Logs/workspace-signout.log" 2>&1 &
  exit 0
fi
sleep 2

if docker info >/dev/null 2>&1 && lstk status >/dev/null 2>&1; then
  log "localstack: stopping"
  if lstk stop </dev/null; then log "localstack: stopped"; else log "localstack: stop failed"; fi
fi

# Ask each app to quit via the Quit item of its app menu, so unsaved work can still prompt.
while IFS= read -r app; do
  item=$(osascript -e "tell application \"System Events\" to tell process \"$app\" to get name of (first menu item of menu 1 of menu bar item 2 of menu bar 1 whose name starts with \"Quit\")" 2>/dev/null)
  # A Quit item ending in an ellipsis opens a confirmation dialog, so use the standard quit signal instead
  if [ -z "$item" ] || [ "${item%…}" != "$item" ]; then
    log "quitting (signal): $app"; signal_app TERM "$app"
  else
    log "quitting: $app"
    osascript -e "tell application \"System Events\" to tell process \"$app\" to click menu item \"$item\" of menu 1 of menu bar item 2 of menu bar 1" >/dev/null 2>&1
  fi
done < <(apps)

# Apps that keep their own state, so they can be force-quit when stuck on an "are you sure?" dialog
SAFE_TO_FORCE='Code|ChatGPT|Granola|Orca|Claude|Slack|Google Chrome|app_mode_loader|Docker Desktop'

# Wait up to N seconds for every app to close.
wait_apps() { for _ in $(seq 1 "$1"); do [ -z "$(apps)" ] && return 0; sleep 1; done; return 1; }

# Escalate: quit signal for anything still open, then force-quit only the known-safe apps.
if ! wait_apps 15; then
  while IFS= read -r app; do log "still open, sending quit signal: $app"; signal_app TERM "$app"; done < <(apps)
  if ! wait_apps 10; then
    while IFS= read -r app; do
      if printf '%s\n' "$app" | grep -qxE "$SAFE_TO_FORCE"; then log "force-quitting: $app"; signal_app KILL "$app"; fi
    done < <(apps)
    wait_apps 5
  fi
fi
left=$(apps | paste -sd, -)
if [ -n "$left" ]; then
  log "still open, not shutting down: $left"
  osascript -e "display notification \"Still open: $left\" with title \"SignOut cancelled\"" >/dev/null 2>&1
  exit 1
fi

log "shutting down"
osascript -e 'tell application "System Events" to shut down'
