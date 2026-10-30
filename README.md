# Developer Setup

Recreate a global developer environment with independent install, configuration, and authentication choices. Skills and agent instructions live in [developer-skills](https://github.com/moneychaudhary/developer-skills).

## Start

```bash
curl -fsSL https://raw.githubusercontent.com/moneychaudhary/developer-setup/main/bootstrap.sh -o /tmp/developer-setup-bootstrap.sh
bash /tmp/developer-setup-bootstrap.sh
```

The bootstrap clones both repositories under `~/projects` and starts setup. Git and Python 3.11+ are required. If Python is missing, the bootstrap offers to install it through Homebrew. On a fresh Mac without Git, install Apple's command-line tools first with `xcode-select --install`.

```bash
# Download both repositories without installing applications.
bash /tmp/developer-setup-bootstrap.sh --clone-only

# Preview everything without changing the machine.
./setup install --all --dry-run

# Select specific agents and editors.
./setup install --install-agents claude_code,codex_cli,cursor_cli --install-vscode --install-orca

# Inspect component IDs.
./setup --list
```

**Enter means Yes. Delete/Backspace means Skip. Ctrl+C saves progress and exits.** Each install or upgrade, global configuration, and supported login has its own choice. Existing applications can skip upgrades while still applying configuration. `--yes` approves selected installation/configuration steps, never browser approval or MFA. Noninteractive installs require an explicit selection.

## Included

- Claude Code, Codex CLI, standalone Cursor CLI, VS Code, and Orca; no Cursor IDE.
- Docker Desktop and Compose, LocalStack CLI and AWS image, Postico 2, and Bruno.
- Homebrew and mise; stable Node, Python, pnpm, uv, and Terraform.
- Git/GitHub CLI, AWS CLI and Session Manager plugin, Azure CLI, PostgreSQL client.
- ripgrep, jq, yq, ShellCheck, shfmt, pre-commit, and Gitleaks.
- Agent LSP, TypeScript/Python language servers, Skill Seekers, agnix, and Crit.
- Captured global VS Code settings and extensions, SF Mono registration from macOS's own fonts, Orca global preferences and source-control prompts, selected Git defaults and Zsh mise activation.
- Global MCP configuration and installation through the independent skills repository.

The catalog is `config/components.json`. There are no project registrations, repository dependencies, per-project hooks, database connections, account sessions, or credentials in the portable configuration. The installer never deploys cloud resources.

## Versions and platforms

The full application adapter targets **macOS**, using Homebrew's platform/architecture resolution. Homebrew formulas can also work on supported Linux installations; macOS casks are reported unavailable elsewhere. Windows native application installation is not implemented. Configuration-only restoration and skills installation can be used independently of application installation.

Setup requests current stable packages. For runtimes, it tries stable releases newest-first, falling back only on an explicit compatibility failure. For incompatible macOS casks, it checks up to 100 upstream recipe revisions for a checksummed compatible release. If a compatible release cannot be verified, the component fails clearly instead of guessing. Upstream binaries and package managers remain authoritative about platform support. VS Code selects compatible extension releases.

Reports record selected versions and fallback reasons. A new run checks versions again; resume preserves completed steps from the original run.

## Resume and authentication

```bash
./setup install --resume
./setup login
./setup login --only claude_code,codex_cli,cursor_cli,github,aws,azure,localstack
./setup doctor
```

Authentication uses native commands and stores credentials in their supported stores, outside these repositories. Where available, status commands preserve existing logins. Docker credential records are detected locally without printing secrets. LocalStack does not expose the same read-only login probe, so setup can offer its native login flow. LocalStack reports completion without claiming independent token validation. AWS SSO access is verified when a single profile or AWS_PROFILE identifies the intended account; otherwise it is reported pending. Run `aws sso login --profile NAME` when needed. Postico license activation remains in its own Settings > License screen. Subscriptions and licenses are not included.

## Configuration and backups

```bash
./setup install --only vscode,shell,git_config --configure-only
./setup capture --output /tmp/developer-settings-export
./setup rollback
```

Selected JSON settings merge with existing keys; VS Code JSONC is accepted and normalized to JSON, with the original backed up. Existing unrelated configuration is retained. Managed files edited after installation are treated as conflicts, rather than overwritten. Rollback restores unchanged managed files; edited files are retained and reported. Applications are never removed by rollback.

Orca must be initialized once and closed before restoring preferences. Setup validates the known database schema and checksum, makes a private local database backup, and changes only the selected global preferences. Account and project fields are preserved. Unknown schemas are refused. Database backups are retained separately; `rollback` does not replace an Orca database automatically.

Local checkpoint, ownership records, private backups, and per-run JSON reports live under `~/.local/state/developer-setup`. Every run prints a final status report and pending actions. Review captured files before publishing them; capture is deliberately an explicit local export.

## Verification

```bash
python3 -m unittest discover -s tests -v
shellcheck bootstrap.sh
./setup install --all --dry-run
./setup install --only vscode,shell,git_config --configure-only --yes --home /tmp/developer-setup-test
```

An alternate `--home` disables system installation, extension installation, and authentication. Tests exercise temporary homes, native provider boundaries, resume, rollback conflicts, JSONC, compatibility selection, and a synthetic Orca database. The tests do not install all applications or simulate a successful human SSO/MFA approval.
