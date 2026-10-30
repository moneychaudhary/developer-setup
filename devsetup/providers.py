import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.request


def version_tuple(value):
    parts = [int(x) for x in re.findall(r'\d+', value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])


def newest_compatible(releases, os_version, arch):
    candidates = [r for r in releases if not r.get('prerelease') and arch in r.get('arch', [arch]) and version_tuple(r.get('min_os', '0')) <= version_tuple(os_version)]
    return max(candidates, key=lambda r: version_tuple(r['version']), default=None)


def run(args, capture=False, env=None):
    result = subprocess.run([str(a) for a in args], text=True, capture_output=capture, env=env)
    if result.returncode:
        raise RuntimeError('Command failed: ' + str(args[0]) + ' (exit ' + str(result.returncode) + ')')
    return result.stdout.strip() if capture else ''


def available(command):
    return shutil.which(command)


def tool_version(component):
    command = component.get('probe', [])
    if not command or not available(command[0]):
        app = component.get('app')
        if app and pathlib.Path('/Applications', app).exists():
            return 'installed'
        return ''
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return (result.stdout or result.stderr).splitlines()[0][:160]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ''


def brew_install(component):
    brew = available('brew')
    if not brew:
        raise RuntimeError('Homebrew is required; select homebrew first.')
    name = component['package']
    if name.count('/') == 2:
        run([brew, 'tap', '/'.join(name.split('/')[:2])])
    cask = component.get('provider') == 'cask'
    flags = ['--cask'] if cask else ['--formula']
    info = json.loads(run([brew, 'info', '--json=v2', *flags, name], capture=True))
    data = info['casks' if cask else 'formulae'][0]
    if cask and platform.system() != 'Darwin':
        raise RuntimeError('This desktop application requires a supported native platform; macOS adapter only.')
    if cask:
        restriction = data.get('depends_on', {}).get('macos', {})
        current = version_tuple(platform.mac_ver()[0])
        for op, values in restriction.items():
            values = values if isinstance(values, list) else [values]
            if op == '>=' and any(current < version_tuple(v) for v in values):
                return historical_cask(component, data, current)
    installed = bool(data.get('installed'))
    greedy = ['--greedy'] if cask else []
    outdated = subprocess.run([brew, 'outdated', '--quiet', *greedy, *flags, name], capture_output=True, text=True)
    if installed and not outdated.stdout.strip():
        return str(data.get('version') or data.get('versions', {}).get('stable', 'current'))
    run([brew, 'upgrade' if installed else 'install', *(greedy if installed else []), *flags, name])
    return str(data.get('version') or data.get('versions', {}).get('stable', 'installed'))


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'developer-setup', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def historical_cask(component, data, current):
    name = data['token']
    tap = data.get('tap', 'homebrew/cask')
    owner, repository = tap.split('/', 1)
    repository = 'homebrew-' + repository
    relative = 'Casks/' + (name[0] + '/' if tap == 'homebrew/cask' else '') + name + '.rb'
    commits = fetch_json(f'https://api.github.com/repos/{owner}/{repository}/commits?path={relative}&per_page=100')
    for commit in commits:
        sha = commit['sha']
        url = f'https://raw.githubusercontent.com/{owner}/{repository}/{sha}/{relative}'
        with urllib.request.urlopen(url, timeout=30) as response:
            recipe = response.read().decode()
        match = re.search(r'depends_on macos: ["\']>= :(\w+)["\']', recipe)
        symbols = {'monterey': '12', 'ventura': '13', 'sonoma': '14', 'sequoia': '15', 'tahoe': '26', 'golden_gate': '27'}
        min_match = re.search(r'depends_on macos:.*?>=\s*(\d+(?:\.\d+)*)', recipe)
        symbol_match = re.search(r'depends_on macos:.*?:(monterey|ventura|sonoma|sequoia|tahoe|golden_gate)', recipe)
        minimum = min_match.group(1) if min_match else symbols.get(symbol_match.group(1)) if symbol_match else None
        if minimum is None or version_tuple(minimum) > current:
            continue
        if 'sha256 :no_check' in recipe or 'version :latest' in recipe:
            continue
        brew = available('brew')
        local_tap = 'moneychaudhary/developer-setup-compat'
        tap_path = pathlib.Path(run([brew, '--repository'], capture=True)) / 'Library/Taps/moneychaudhary/homebrew-developer-setup-compat'
        if not tap_path.exists():
            run([brew, 'tap-new', local_tap])
        target = tap_path / 'Casks' / (name + '.rb')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(recipe)
        run([brew, 'install', '--cask', local_tap + '/' + name])
        found = re.search(r'version "([^"]+)"', recipe)
        return (found.group(1) if found else sha[:12]) + ' (OS-compatible historical release)'
    raise RuntimeError('No verified compatible stable cask found in the latest 100 upstream recipe changes; skipped.')


def install(component):
    provider = component['provider']
    if provider == 'homebrew':
        if available('brew'):
            run(['brew', 'update'])
            return run(['brew', '--version'], capture=True).splitlines()[0]
        with tempfile.TemporaryDirectory() as temp:
            script = pathlib.Path(temp) / 'install.sh'
            urllib.request.urlretrieve('https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh', script)
            run(['/bin/bash', script])
        os.environ['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + os.environ.get('PATH', '')
    elif provider in ('formula', 'cask'):
        return brew_install(component)
    elif provider == 'mise':
        if not available('mise'):
            raise RuntimeError('mise is required; select mise first.')
        tool = component['package']
        versions = run(['mise', 'ls-remote', tool], capture=True).splitlines()
        stable = sorted({v for v in versions if re.fullmatch(r'\d+\.\d+\.\d+', v)}, key=version_tuple, reverse=True)
        for value in stable[:100]:
            if tool == 'python' and version_tuple(value) < (3, 11, 0):
                continue
            result = subprocess.run(['mise', 'install', tool + '@' + value], capture_output=True, text=True)
            if result.returncode:
                diagnostic = (result.stdout + result.stderr).lower()
                unsupported = any(word in diagnostic for word in ('unsupported', 'incompatible', 'requires macos', 'requires mac os', 'glibc', 'bad cpu type'))
                if unsupported:
                    continue
                raise RuntimeError('mise installation failed; no downgrade attempted for network or unrelated failures. Run mise install ' + tool + '@' + value + ' for diagnostics.')
            run(['mise', 'use', '--global', tool + '@' + value])
            return value + (' (newest installable stable release)' if value != stable[0] else '')
        raise RuntimeError('No compatible stable ' + tool + ' release installed; review mise diagnostics before retrying.')
    elif provider == 'npm':
        run(['npm', 'install', '--global', component['package'] + '@latest'])
    elif provider == 'uv':
        run(['uv', 'tool', 'install', '--upgrade', component['package']])
    elif provider == 'cursor':
        with tempfile.TemporaryDirectory() as temp:
            script = pathlib.Path(temp) / 'cursor-install.sh'
            urllib.request.urlretrieve('https://cursor.com/install', script)
            run(['/bin/bash', script])
    elif provider == 'orca_skills':
        run(['orca', 'skills', 'install', '--all'])
    elif provider == 'image':
        run(['docker', 'pull', component['package'] + ':latest'])
    else:
        raise RuntimeError('Unsupported installation provider: ' + provider)
    return tool_version(component) or 'installed; version probe unavailable'
