import shutil
import json
import os
from pathlib import Path
import subprocess

COMMANDS = {
    'claude_code': (['claude', 'auth', 'status'], ['claude', 'auth', 'login']),
    'codex_cli': (['codex', 'login', 'status'], ['codex', 'login']),
    'cursor_cli': (['agent', 'status'], ['agent', 'login']),
    'github': (['gh', 'auth', 'status'], ['gh', 'auth', 'login']),
    'aws': (['aws', 'sts', 'get-caller-identity'], ['aws', 'configure', 'sso']),
    'azure': (['az', 'account', 'show'], ['az', 'login']),
    'localstack': ([], ['lstk', 'login']),
    'docker': ([], ['docker', 'login']),
}


def signed_in(name):
    probe, _ = COMMANDS[name]
    if name == 'docker':
        folder = Path(os.environ.get('DOCKER_CONFIG', str(Path.home() / '.docker')))
        path = folder / 'config.json'
        try:
            config = json.loads(path.read_text())
            if any(bool(value) for value in config.get('auths', {}).values()):
                return True
            helper = config.get('credsStore')
            if helper and shutil.which('docker-credential-' + helper):
                listed = subprocess.run(['docker-credential-' + helper, 'list'],capture_output=True,text=True,timeout=10)
                return listed.returncode == 0 and bool(json.loads(listed.stdout))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return False
    if not probe or not shutil.which(probe[0]):
        return False
    try:
        result = subprocess.run(probe, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def login(name):
    _, command = COMMANDS[name]
    if not shutil.which(command[0]):
        raise RuntimeError('Install ' + command[0] + ' before logging in.')
    result = subprocess.run(command)
    if result.returncode:
        raise RuntimeError('Authentication command did not complete successfully.')
    if name == 'aws':
        profiles = subprocess.run(['aws','configure','list-profiles'],capture_output=True,text=True,check=True).stdout.splitlines()
        profile = os.environ.get('AWS_PROFILE') or (profiles[0] if len(profiles) == 1 else '')
        if not profile:
            return 'configured; choose a profile with aws sso login --profile NAME and verify aws sts get-caller-identity --profile NAME'
        logged_in = subprocess.run(['aws','sso','login','--profile',profile])
        if logged_in.returncode == 0:
            verified = subprocess.run(['aws','sts','get-caller-identity','--profile',profile],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if verified.returncode == 0:
                return 'authenticated AWS SSO profile ' + profile
        return 'configured; AWS SSO access verification remains pending for profile ' + profile
    if name == 'localstack':
        return 'Native LocalStack login completed; no read-only token status command is exposed by this CLI.'
    if name == 'docker':
        return 'authenticated'
    if not signed_in(name):
        raise RuntimeError('Login finished, but verification is pending; credentials were not exported.')
    return 'authenticated'
