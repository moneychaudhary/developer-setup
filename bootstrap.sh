#!/usr/bin/env bash
set -euo pipefail

projects_dir="${HOME}/projects"
clone_only=false
approve=false
forward=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --clone-only) clone_only=true ;;
    --projects-dir) projects_dir="$2"; shift ;;
    --yes) approve=true; forward+=(--yes) ;;
    --help|-h)
      echo 'Usage: bash bootstrap.sh [--clone-only] [--projects-dir PATH] [setup options]'
      echo 'Clones developer-setup and developer-skills, then starts interactive setup.'
      exit 0 ;;
    *) forward+=("$1") ;;
  esac
  shift
done

ask_bootstrap() {
  local key
  printf '%s [Enter] Yes · [Delete/Backspace] Skip\n' "$1"
  if [ ! -t 0 ]; then
    echo 'A terminal is required; pass --yes for unattended prerequisite installation.' >&2
    return 1
  fi
  while IFS= read -r -s -n 1 key; do
    case "$key" in
      '') printf '\n'; return 0 ;;
      $'\177'|$'\010') printf '\nSkipped\n'; return 1 ;;
    esac
  done
  return 1
}

if ! command -v git >/dev/null 2>&1 || ! git --version >/dev/null 2>&1; then
  echo 'Git is required to clone the repositories. Install Git (macOS: xcode-select --install), then rerun.' >&2
  exit 1
fi
mkdir -p "$projects_dir"
for repo in developer-setup developer-skills; do
  source_url="https://github.com/moneychaudhary/${repo}.git"
  if [ -n "${DEVELOPER_SETUP_SOURCE_ROOT:-}" ]; then
    source_url="${DEVELOPER_SETUP_SOURCE_ROOT}/${repo}"
  fi
  destination="${projects_dir}/${repo}"
  if [ -e "$destination" ]; then
    if [ ! -d "$destination/.git" ]; then
      echo "Refusing to replace an existing non-repository directory: $destination" >&2
      exit 1
    fi
    actual_url="$(git -C "$destination" remote get-url origin)"
    if [ "$actual_url" != "$source_url" ]; then
      echo "Existing repository has another origin; left untouched: $destination" >&2
      exit 1
    fi
    if [ -n "$(git -C "$destination" status --porcelain)" ]; then
      echo "Keeping existing local changes in $destination"
    else
      git -C "$destination" pull --ff-only
    fi
  else
    git clone "$source_url" "$destination"
  fi
done
if "$clone_only"; then
  echo "Repositories ready under $projects_dir"
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  if "$approve" || ask_bootstrap 'Install Python 3.11+ using Homebrew?'; then
    if ! command -v brew >/dev/null 2>&1; then
      if "$approve" || ask_bootstrap 'Install Homebrew? Administrator authentication may be requested.'; then
        installer="$(mktemp)"
        trap 'rm -f "$installer"' EXIT
        curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer"
        /bin/bash "$installer"
        export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
      else
        echo 'Python prerequisite skipped. Repositories are downloaded; install Python 3.11+ to continue.'
        exit 0
      fi
    fi
    brew install python
    brew_prefix="$(brew --prefix)"
    export PATH="${brew_prefix}/bin:$PATH"
  else
    echo 'Python prerequisite skipped. Repositories are downloaded; install Python 3.11+ to continue.'
    exit 0
  fi
fi
exec python3 "$projects_dir/developer-setup/setup" install "${forward[@]}"
