import argparse
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys

from . import auth, config, providers
from .state import State
from .ui import ask

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'config/components.json').read_text())
BY_ID = {c['id']: c for c in CATALOG}
AGENTS = ['claude_code', 'codex_cli', 'cursor_cli']
SUCCESS = {'installed', 'updated', 'already-current', 'configured', 'authenticated', 'login-completed'}


def parser():
    p = argparse.ArgumentParser(description='Install a portable global developer environment. Enter = Yes; Delete/Backspace = Skip.')
    p.add_argument('command', choices=['install', 'login', 'doctor', 'capture', 'rollback', 'update', 'diff'], nargs='?', default='install')
    p.add_argument('--all', action='store_true', help='Select all components; interactive confirmation remains unless --yes.')
    p.add_argument('--only', help='Comma-separated component IDs; see --list.')
    p.add_argument('--install-agents', help='all or claude_code,codex_cli,cursor_cli')
    for name in ('vscode', 'orca'):
        p.add_argument('--install-' + name, action='store_true')
    p.add_argument('--orca-settings', choices=['current'], help='Restore bundled allowlisted global settings.')
    p.add_argument('--login', action='store_true', help='Offer authentication after installation.')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--yes', action='store_true', help='Approve selected install/config steps; never approve interactive logins.')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--home', type=pathlib.Path, default=pathlib.Path.home(), help='Override configuration home; system installs are disabled for an alternate home.')
    p.add_argument('--configure-only', action='store_true')
    p.add_argument('--no-extensions', action='store_true', help='Restore VS Code settings without running its extension installer.')
    p.add_argument('--output', type=pathlib.Path, help='Explicit destination for capture (never captures credentials).')
    p.add_argument('--list', action='store_true')
    return p


def select(args):
    names = set(BY_ID) if args.all else set()
    if args.only:
        names.update(args.only.split(','))
    if args.install_agents:
        agents = AGENTS if args.install_agents == 'all' else args.install_agents.split(',')
        if set(agents) - set(AGENTS):
            raise RuntimeError('Unknown agent; choose ' + ','.join(AGENTS))
        names.update(agents)
    for name in ('vscode', 'orca'):
        if getattr(args, 'install_' + name):
            names.add(name)
    unknown = names - set(BY_ID)
    if unknown:
        raise RuntimeError('Unknown components: ' + ', '.join(sorted(unknown)))
    if not names:
        if args.command in ('doctor', 'diff'):
            names = set(BY_ID)
        elif args.command == 'login':
            return [c for c in CATALOG if c['id'] in auth.COMMANDS]
        elif args.yes or args.dry_run:
            raise RuntimeError('Choose --all, --only, or --install-agents explicitly.')
        elif not sys.stdin.isatty():
            raise RuntimeError('Interactive setup needs a terminal; use explicit selection with --yes or --dry-run.')
        else:
            names = set(BY_ID)
    if not args.configure_only and args.command not in ('login', 'doctor', 'diff'):
        def add_dependencies(name):
            for dep in BY_ID[name].get('requires', []):
                if dep not in names:
                    names.add(dep)
                    add_dependencies(dep)
        for name in list(names):
            add_dependencies(name)
    ordered, seen = [], set()
    def visit(name):
        if name in seen:
            return
        seen.add(name)
        for dep in BY_ID[name].get('requires', []):
            if dep in names:
                visit(dep)
        ordered.append(BY_ID[name])
    for c in CATALOG:
        if c['id'] in names:
            visit(c['id'])
    return ordered


def configure_component(name, home, managed, args):
    if name == 'vscode':
        config.configure_vscode(home, managed, extensions=not args.no_extensions)
    elif name == 'orca':
        return 'Database backup: ' + config.configure_orca(home, managed.root.parent)
    elif name == 'fonts':
        return config.configure_fonts(home, managed)
    elif name == 'shell':
        config.configure_shell(home, managed)
    elif name == 'git_config':
        config.configure_git(home, managed)
    elif name == 'integrations':
        from .integrations import configure
        configure(home, managed)
    else:
        return None
    return 'Global configuration applied; unrelated keys retained.'


def skill_install(home, args):
    sibling = ROOT.parent / 'developer-skills'
    if not (sibling / 'skills').exists():
        sibling = home / 'projects/developer-skills'
    if not (sibling / 'skills').exists():
        raise RuntimeError('Clone https://github.com/moneychaudhary/developer-skills alongside this repository, or use bootstrap.sh.')
    command = [str(sibling / 'skills'), 'install', '--agents', ','.join(AGENTS), '--home', str(home)]
    command.append('--yes')
    providers.run(command)


def refresh_path():
    paths = [str(pathlib.Path.home() / '.local/bin'), '/opt/homebrew/bin', '/usr/local/bin', '/opt/homebrew/opt/libpq/bin', '/usr/local/opt/libpq/bin']
    os.environ['PATH'] = os.pathsep.join(paths + [os.environ.get('PATH', '')])
    if shutil.which('mise'):
        try:
            env = json.loads(providers.run(['mise', 'env', '--json'], capture=True))
            if env.get('PATH'):
                os.environ['PATH'] = env['PATH'] + os.pathsep + os.environ['PATH']
        except (RuntimeError, ValueError):
            pass


def attempt(state, step, action, args, success):
    previous = state.data['steps'].get(step, {})
    if args.resume and previous.get('status') in SUCCESS:
        print(step + ': keeping completed step from this run')
        return True
    if not args.yes and not ask(step + '?'):
        state.mark(step, 'skipped')
        return False
    state.mark(step, 'running')
    try:
        detail = action() or ''
        state.mark(step, success, detail=detail)
        return True
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        state.mark(step, 'failed', detail=str(exc))
        return False


def run_install(args, selected, state, home):
    managed = config.ManagedFiles(home, state.root)
    alternate = home.resolve() != pathlib.Path.home().resolve()
    for component in selected:
        name = component['id']
        refresh_path()
        if component['provider'] == 'skills':
            attempt(state, name + '.install', lambda: skill_install(home, args), args, 'installed')
            continue
        if component['provider'] != 'config' and not args.configure_only:
            if alternate:
                state.mark(name + '.install', 'pending', detail='System installation disabled for --home isolation.')
                continue
            print('\n' + component['label'] + ': ' + (providers.tool_version(component) or 'not installed'))
            before = providers.tool_version(component)
            completed = attempt(state, name + '.install', lambda c=component: providers.install(c), args, 'installed')
            if not completed and not before:
                continue
            if completed:
                after = providers.tool_version(component)
                if not args.resume:
                    state.data['steps'][name + '.install']['status'] = 'already-current' if before and before == after else 'updated' if before else 'installed'
                state.data['steps'][name + '.install']['version'] = after
                state.save()
        if name in ('vscode', 'orca', 'shell', 'git_config', 'integrations', 'fonts'):
            attempt(state, name + '.configure', lambda n=name: configure_component(n, home, managed, args), args, 'configured')
        if component['provider'] == 'cask' and name not in auth.COMMANDS:
            state.mark(name + '.login', 'not-required', detail='No account login required for local use.')
        if name == 'postico2':
            state.mark('postico2.license', 'pending', detail='Optional: activate your purchased license in Postico 2 Settings > License; evaluation needs no login.')
        if name in auth.COMMANDS:
            if args.resume and state.data['steps'].get(name + '.login', {}).get('status') in ('authenticated', 'login-completed') and (name == 'localstack' or auth.signed_in(name)):
                print(name + ': keeping completed login from this run')
                continue
            if alternate:
                state.mark(name + '.login', 'pending', detail='Authentication disabled for alternate configuration home.')
                continue
            if auth.signed_in(name):
                state.mark(name + '.login', 'authenticated', detail='Existing session retained.')
            elif (args.login or sys.stdin.isatty()) and sys.stdin.isatty():
                if ask('Log in to ' + component['label'] + '?'):
                    try:
                        detail = auth.login(name)
                        state.mark(name + '.login', 'pending' if name == 'aws' and not detail.startswith('authenticated') else 'login-completed' if name == 'localstack' else 'authenticated', detail=detail)
                    except (RuntimeError, OSError) as exc:
                        state.mark(name + '.login', 'failed', detail=str(exc))
                else:
                    state.mark(name + '.login', 'skipped')
            else:
                state.mark(name + '.login', 'pending', detail='Run ./setup login --only ' + name + ' in a terminal.')


def capture(home, destination):
    if destination is None:
        raise RuntimeError('Capture requires --output DIRECTORY; review its contents before publishing.')
    destination.mkdir(parents=True, exist_ok=True)
    user = config.code_user(home)
    settings = user / 'settings.json'
    if settings.exists():
        from . import jsonc
        data = jsonc.loads(settings.read_text())
        allow = json.loads((ROOT / 'config/vscode-settings.json').read_text())
        values = {k: data[k] for k in allow if k in data}
        from .state import atomic_json
        atomic_json(destination / 'vscode-settings.json', values)
    extension_index = home / '.vscode/extensions/extensions.json'
    if extension_index.exists():
        entries = json.loads(extension_index.read_text())
        from .state import atomic_json
        atomic_json(destination / 'vscode-extensions.json', sorted({item['identifier']['id'] for item in entries}))
    for name in ('keybindings.json',):
        source = user / name
        if source.exists():
            shutil.copy2(source, destination / name)
    snippet_source = user / 'snippets'
    if snippet_source.exists():
        shutil.copytree(snippet_source, destination / 'snippets', dirs_exist_ok=True)
    db = config.orca_database(home)
    if db.exists():
        import sqlite3
        with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True) as connection:
            row = connection.execute("SELECT payload FROM profile_state_documents WHERE domain='settings'").fetchone()
        from .state import atomic_json
        atomic_json(destination / 'orca-settings.json', config.portable_orca(json.loads(row[0])))
    print('Captured selected global preferences to', destination)


def main(argv=None):
    args = parser().parse_args(argv)
    if args.list:
        for c in CATALOG:
            print(c['id'].ljust(22) + c['label'])
        return 0
    home = args.home.expanduser().resolve()
    try:
        if args.dry_run and args.command in ('capture', 'rollback'):
            print('Read-only plan: ' + args.command + '; no files changed.')
            return 0
        if args.command == 'login' and home != pathlib.Path.home().resolve():
            raise RuntimeError('Login is disabled for an alternate --home; no host credentials were changed.')
        if args.configure_only and home != pathlib.Path.home().resolve():
            args.no_extensions = True
        if args.command == 'capture':
            capture(home, args.output)
            return 0
        if args.command == 'rollback':
            conflicts = config.ManagedFiles(home, home / '.local/state/developer-setup').rollback()
            print('Configuration rollback complete. Edited files retained:', ', '.join(conflicts) or 'none')
            print('Applications and Orca database backups are retained; no applications were uninstalled.')
            return int(bool(conflicts))
        if args.resume and not args.only and not args.all and not args.install_agents:
            checkpoint = home / '.local/state/developer-setup/checkpoint.json'
            if checkpoint.exists():
                args.only = ','.join(json.loads(checkpoint.read_text()).get('selection', []))
        if args.command == 'update':
            args.command = 'install'
        selected = select(args)
        if args.command == 'diff':
            import difflib
            from . import jsonc
            target = config.code_user(home) / 'settings.json'
            if any(c['id'] == 'vscode' for c in selected):
                original = target.read_text() if target.exists() else '{}\n'
                current = jsonc.loads(original)
                incoming = json.loads((ROOT / 'config/vscode-settings.json').read_text())
                desired = json.dumps(config.deep_merge(current, incoming), indent=4) + '\n'
                print(''.join(difflib.unified_diff(original.splitlines(True), desired.splitlines(True), fromfile=str(target), tofile='saved VS Code settings')) or 'VS Code settings already match.')
            print('Other selected components: ' + ', '.join(c['id'] for c in selected if c['id'] != 'vscode'))
            print('No files changed. Orca preferences and managed files are reviewed separately during configuration.')
            return 0
        if args.dry_run:
            print('Read-only plan; latest OS-compatible stable releases; no authentication performed.')
            for c in selected:
                print(c['id'] + ': ' + c['provider'] + ' ' + c['package'])
            return 0
        if args.command == 'doctor':
            refresh_path()
            from .doctor import check
            return check(selected, home)
        if args.command == 'login' and not sys.stdin.isatty():
            raise RuntimeError('Login needs an interactive terminal for browser approval or MFA.')
        state = State(home / '.local/state/developer-setup', args.command, resume=args.resume)
        if args.resume:
            selected = [BY_ID[n] for n in state.data['selection']]
            for option, value in state.data.get('options', {}).items():
                setattr(args, option, value)
        else:
            state.data['selection'] = [c['id'] for c in selected]
            state.data['options'] = {name: getattr(args, name) for name in ('configure_only', 'no_extensions', 'yes', 'login')}
            state.save()
        try:
            if args.command == 'install':
                run_install(args, selected, state, home)
            else:
                for c in selected:
                    if c['id'] not in auth.COMMANDS:
                        continue
                    name = c['id']
                    if auth.signed_in(name):
                        state.mark(name + '.login', 'authenticated', detail='Existing session retained.')
                    elif ask('Log in to ' + c['label'] + '?'):
                        try:
                            detail = auth.login(name)
                            state.mark(name + '.login', 'pending' if name == 'aws' and not detail.startswith('authenticated') else 'login-completed' if name == 'localstack' else 'authenticated', detail=detail)
                        except (RuntimeError, OSError) as exc:
                            state.mark(name + '.login', 'failed', detail=str(exc))
                    else:
                        state.mark(name + '.login', 'skipped')
            state.data['finished'] = True
        except KeyboardInterrupt:
            state.data['finished'] = False
            for key, value in list(state.data['steps'].items()):
                if value['status'] == 'running':
                    state.mark(key, 'interrupted', detail='Verify actual state before resuming.')
            print('\nInterrupted. Progress saved.')
        finally:
            state.save()
            state.report()
        return int(not state.data['finished'] or any(v['status'] == 'failed' for v in state.data['steps'].values()))
    except (RuntimeError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
