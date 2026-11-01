-- Confirm, then hand off to the sign-out script, which quits every app and shuts down
display dialog "Close all apps, stop LocalStack and Docker, and shut down this Mac?" buttons {"Cancel", "Shut Down"} default button "Cancel" cancel button "Cancel" with title "SignOut" with icon caution
do shell script "$HOME/.local/share/workspace/signout.sh >> $HOME/Library/Logs/workspace-signout.log 2>&1"
