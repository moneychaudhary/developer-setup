import json
import os
import signal
import pathlib
import shutil
import subprocess
from . import config, providers


def mcp_handshake(server):
    import queue
    import threading
    import time
    process = None
    messages = queue.Queue()
    try:
        process = subprocess.Popen([server['command'], *server.get('args', [])], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1, start_new_session=(os.name != 'nt'))
        def read_messages():
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    continue
        reader = threading.Thread(target=read_messages, daemon=True)
        reader.start()
        deadline = time.monotonic() + 25
        def send(message):
            process.stdin.write(json.dumps(message) + '\n')
            process.stdin.flush()
        def response(identifier):
            while time.monotonic() < deadline:
                try:
                    message = messages.get(timeout=max(0.01, deadline-time.monotonic()))
                except queue.Empty:
                    return None
                if message.get('id') == identifier:
                    return message.get('result')
            return None
        send({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'developer-setup-doctor','version':'1'}}})
        if response(1) is None:
            return False, 0
        send({'jsonrpc':'2.0','method':'notifications/initialized'})
        send({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
        result = response(2)
        tools = result.get('tools') if isinstance(result, dict) else None
        return isinstance(tools, list), len(tools) if isinstance(tools, list) else 0
    except (OSError, subprocess.SubprocessError):
        return False, 0
    finally:
        if process is not None:
            if os.name != 'nt':
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name != 'nt':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
            reader.join(timeout=1)
            process.stdin.close()
            process.stdout.close()


def check(selected, home):
    failed=False
    for component in selected:
        name=component['id']
        if component['provider'] not in ('config','skills','image','orca_skills'):
            version=providers.tool_version(component)
            print(name + ': ' + (version or 'missing'))
            failed=failed or not bool(version)
        elif name=='skills':
            sibling=pathlib.Path(__file__).resolve().parents[2]/'developer-skills/skills'
            if sibling.exists():
                result=subprocess.run([str(sibling),'doctor','--agents','all','--home',str(home)])
                failed=failed or result.returncode!=0
            else:
                print('skills: missing sibling repository')
                failed=True
        elif name=='integrations':
            path=home/'.cursor/mcp.json'
            servers=json.loads(path.read_text()).get('mcpServers',{}) if path.exists() else {}
            for name in ('lsp','skill-seekers'):
                if name not in servers:
                    print('MCP '+name+': not configured')
                    failed=True
                    continue
                ok,count=mcp_handshake(servers[name])
                print('MCP '+name+': '+(str(count)+' tools available' if ok else 'handshake failed'))
                failed=failed or not ok
        elif name=='localstack_image':
            try:
                result=subprocess.run(['docker','image','inspect','localstack/localstack:latest'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                print('localstack_image: '+('available' if result.returncode==0 else 'missing or Docker stopped'))
                failed=failed or result.returncode!=0
            except (OSError,subprocess.TimeoutExpired):
                print('localstack_image: Docker unavailable')
                failed=True
        elif name=='shell':
            path=home/'.zshrc'
            ok=path.exists() and '# developer-setup begin' in path.read_text()
            print('shell: '+('configured' if ok else 'not managed'))
            failed=failed or not ok
        elif name=='git_config':
            ok=(home/'.config/developer-setup/gitconfig').exists()
            print('git_config: '+('configured' if ok else 'not managed'))
            failed=failed or not ok
    return int(failed)
