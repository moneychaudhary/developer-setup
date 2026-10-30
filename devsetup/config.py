import hashlib
from contextlib import closing
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import time

from .state import atomic_json
from . import jsonc

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORCA_KEYS = '''nestWorkspaces refreshLocalBaseRefOnWorktreeCreate autoRenameBranchFromWork branchPrefix branchPrefixCustom theme uiLanguage appIcon appFontFamily editorAutoSave editorAutoSaveDelayMs editorMinimapEnabled editorFontFamily editorWordWrap richMarkdownSpellcheckEnabled markdownReviewToolsEnabled terminalFontSize terminalFontFamily terminalFontWeight terminalFontWeightBold terminalLineHeight terminalScrollSensitivity terminalFastScrollSensitivity terminalTuiScrollSensitivity terminalGpuAcceleration terminalLigatures terminalInlineImages terminalCursorStyle terminalCursorBlink terminalThemeDark terminalThemeLight terminalUseSeparateLightTheme terminalInactivePaneOpacity terminalActivePaneOpacity terminalDividerThicknessPx terminalRightClickToPaste terminalMouseHideWhileTyping terminalFocusFollowsMouse windowBackgroundBlur minimizeToTrayOnClose showMenuBarIcon terminalClipboardOnSelect terminalCopyTrimsGutter terminalAllowOsc52Clipboard claudeAgentTeamsMode terminalScrollbackRows openLinksInApp experimentalNativeChat nativeChatResumeWorkOnRestart nativeChatQueueFollowUps nativeChatInlineVisuals nativeChatInheritShellEnvironment nativeChatPermissionMode rightSidebarOpenByDefault showGitIgnoredFiles followSymlinkedDirectories sourceControlViewMode sourceControlCompareAgainstUpstream showTitlebarAppName showTasksButton showAutomationsButton artifactsEnabled nestedWorkerMaxDepth orchestrationChatErrorEscalationEnabled orchestrationHeartbeatsEnabled orchestrationHeartbeatIntervalMinutes showSkillsButton ctrlTabOrderMode terminalShortcutPolicy diffDefaultView diffWordWrap diffShowWhitespace diffCollapseUnchangedRegions defaultTuiAgent pluginSystemEnabled disabledPlugins agentPermissionDefault agentPermissionOverrides agentStatusHooksEnabled claudeSubagentNavigationEnabled agentWorkspaceTrustEnabled tabAutoGenerateTitle confirmClosePinnedTab editorPreviewTabsEnabled keepComputerAwakeWhileAgentsRun terminalMacOptionAsAlt compactWorktreeCards nativeChatAppearance nativeChatProviders'''.split()


def portable_orca(settings):
    result = {k: settings[k] for k in ORCA_KEYS if k in settings}
    source = settings.get('sourceControlAi', {})
    if source:
        result['sourceControlAi'] = {k: source[k] for k in ('enabled', 'instructionsByOperation', 'prCreationDefaults') if k in source}
        result['sourceControlAi']['actions'] = {
            name: {k: action[k] for k in ('commandInputTemplate', 'agentArgs') if k in action}
            for name, action in source.get('actions', {}).items()
        }
    return result


def deep_merge(current, incoming):
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            deep_merge(current[key], value)
        else:
            current[key] = value
    return current


class ManagedFiles:
    def __init__(self, home, state_dir):
        self.home = home.resolve()
        self.root = state_dir / 'managed'
        self.index = self.root / 'index.json'
        self.records = json.loads(self.index.read_text()) if self.index.exists() else {}

    def write(self, target, text):
        target = target.expanduser()
        target.resolve().relative_to(self.home)
        key = str(target)
        if target.is_symlink():
            raise RuntimeError('Refusing to replace a symlinked configuration file: ' + str(target))
        original = target.read_bytes() if target.exists() else None
        if key in self.records and hashlib.sha256(original or b'').hexdigest() != self.records[key]['installed_hash']:
            raise RuntimeError('Managed file is locally modified; preserve edits and review before retrying: ' + str(target))
        data = text.encode() if isinstance(text, str) else text
        if original == data:
            return
        token = hashlib.sha256(key.encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if key not in self.records:
            backup = self.root / (token + '.bak')
            if original is not None:
                backup.write_bytes(original)
                backup.chmod(0o600)
            self.records[key] = {'backup': str(backup) if original is not None else None}
        temp = target.with_name(target.name + '.developer-setup.tmp')
        target.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(data)
        temp.chmod(0o600)
        os.replace(temp, target)
        self.records[key]['installed_hash'] = hashlib.sha256(target.read_bytes()).hexdigest()
        atomic_json(self.index, self.records)

    def merge_json(self, target, values):
        current = jsonc.loads(target.read_text()) if target.exists() else {}
        self.write(target, json.dumps(deep_merge(current, values), indent=4) + '\n')

    def rollback(self):
        conflicts = []
        for key, record in list(self.records.items()):
            target = pathlib.Path(key)
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != record['installed_hash']:
                conflicts.append(key)
                continue
            if record['backup']:
                target.write_bytes(pathlib.Path(record['backup']).read_bytes())
            else:
                target.unlink(missing_ok=True)
            del self.records[key]
        atomic_json(self.index, self.records)
        return conflicts


def code_user(home):
    import platform
    if platform.system() == 'Darwin':
        return home / 'Library/Application Support/Code/User'
    if os.name == 'nt':
        return home / 'AppData/Roaming/Code/User'
    return home / '.config/Code/User'


def configure_vscode(home, managed, extensions=True):
    folder = code_user(home)
    managed.merge_json(folder / 'settings.json', json.loads((ROOT / 'config/vscode-settings.json').read_text()))
    for name in ('keybindings.json',):
        source = ROOT / 'config' / name
        if source.exists():
            managed.write(folder / name, source.read_text())
    source = ROOT / 'config/snippets'
    if source.exists():
        for path in source.iterdir():
            if path.is_file():
                managed.write(folder / 'snippets' / path.name, path.read_text())
    if extensions:
        from .providers import run
        for extension in json.loads((ROOT / 'config/vscode-extensions.json').read_text()):
            run(['code', '--install-extension', extension, '--force'])


def orca_database(home):
    base = home / 'Library/Application Support/orca' if __import__('platform').system() == 'Darwin' else home / '.config/orca'
    index = base / 'orca-profile-index.json'
    profile = 'local-default'
    if index.exists():
        data = json.loads(index.read_text())
        profile = data.get('activeProfileId', profile)
    if '/' in profile or '\\' in profile or profile in ('.', '..'):
        raise RuntimeError('Invalid Orca profile identifier.')
    return base / 'profiles' / profile / 'profile-state.db'


def configure_orca(home, state_dir):
    processes = subprocess.run(['ps', '-axo', 'command='], capture_output=True, text=True, check=True).stdout
    if any('/Orca.app/Contents/' in line or 'orca-ide' in line or '/orcad/' in line for line in processes.splitlines()):
        raise RuntimeError('Close Orca before restoring global settings, then resume. No live database was modified.')
    path = orca_database(home)
    if not path.exists():
        raise RuntimeError('Start Orca once to initialize a profile, close it, then resume configuration.')
    with closing(sqlite3.connect('file:' + str(path) + '?mode=rw', uri=True)) as db, db:
        columns = [r[1] for r in db.execute('PRAGMA table_info(profile_state_documents)')]
        if columns != ['domain', 'payload', 'domain_version', 'revision', 'updated_at', 'content_hash']:
            raise RuntimeError('Unsupported Orca profile schema; settings left unchanged.')
        row = db.execute("SELECT payload,domain_version,content_hash FROM profile_state_documents WHERE domain='settings'").fetchone()
        if row is None or row[1] != 1 or hashlib.sha256(row[0].encode()).hexdigest() != row[2]:
            raise RuntimeError('Orca settings schema or checksum could not be verified.')
        backup = state_dir / 'orca-backups' / (str(time.time_ns()) + '.db')
        backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(sqlite3.connect(backup)) as dest, dest:
            db.backup(dest)
        backup.chmod(0o600)
        db.execute('BEGIN IMMEDIATE')
        revision = int(db.execute("SELECT value FROM profile_state_meta WHERE key='revision'").fetchone()[0]) + 1
        current = json.loads(row[0])
        incoming = portable_orca(json.loads((ROOT / 'config/orca-settings.json').read_text()))
        payload = json.dumps(deep_merge(current, incoming), ensure_ascii=False, separators=(',', ':'))
        db.execute("UPDATE profile_state_documents SET payload=?,revision=?,updated_at=?,content_hash=? WHERE domain='settings'", (payload, revision, int(time.time()*1000), hashlib.sha256(payload.encode()).hexdigest()))
        db.execute("UPDATE profile_state_meta SET value=? WHERE key='revision'", (str(revision),))
    return str(backup)


def configure_shell(home, managed):
    path = home / '.zshrc'
    text = path.read_text() if path.exists() else ''
    begin, end = '# developer-setup begin', '# developer-setup end'
    block = '''# developer-setup begin
export PATH="$HOME/.local/bin:/opt/homebrew/opt/libpq/bin:/usr/local/opt/libpq/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if command -v mise >/dev/null 2>&1; then
  eval "$(mise activate zsh)"
fi
# developer-setup end'''
    if begin in text and end in text:
        text = text[:text.index(begin)] + block + text[text.index(end)+len(end):]
    else:
        text += '\n' + block + '\n'
    managed.write(path, text)


def configure_git(home, managed):
    path = home / '.gitconfig'
    text = path.read_text() if path.exists() else ''
    include = '[include]\n\tpath = ~/.config/developer-setup/gitconfig\n'
    managed.write(home / '.config/developer-setup/gitconfig', (ROOT / 'config/gitconfig').read_text())
    if 'path = ~/.config/developer-setup/gitconfig' not in text:
        managed.write(path, text + '\n' + include)


def configure_fonts(home, managed):
    source = pathlib.Path('/System/Applications/Utilities/Terminal.app/Contents/Resources/Fonts')
    if not source.exists():
        return 'SF Mono is unavailable on this OS; configured monospace fallbacks remain active.'
    for font in source.glob('SF-Mono-*.otf'):
        managed.write(home / 'Library/Fonts' / font.name, font.read_bytes())
    return 'Registered the SF Mono fonts already supplied by macOS; no proprietary fonts redistributed.'
