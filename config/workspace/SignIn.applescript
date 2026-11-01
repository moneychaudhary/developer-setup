-- Run the workspace sign-in script and log to ~/Library/Logs/workspace-signin.log
do shell script "$HOME/.local/share/workspace/signin.sh >> $HOME/Library/Logs/workspace-signin.log 2>&1"
