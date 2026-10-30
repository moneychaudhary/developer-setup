import json
import pathlib
import shutil


def configure(home, managed):
    def executable(name):
        path = shutil.which(name)
        if not path:
            raise RuntimeError('Missing MCP dependency: ' + name)
        return path
    uv = executable('uv')
    lsp = executable('agent-lsp')
    servers = {
        'lsp': {'command': lsp, 'args': ['typescript:' + executable('typescript-language-server') + ',--stdio', 'python:' + executable('pyright-langserver') + ',--stdio']},
        'skill-seekers': {'command': uv, 'args': ['tool', 'run', '--from', 'skill-seekers', 'python', '-m', 'skill_seekers.mcp.server_fastmcp']},
    }
    for path in (home / '.claude.json', home / '.cursor/mcp.json'):
        managed.merge_json(path, {'mcpServers': servers})
    paths = [home / '.codex/config.toml']
    accounts = home / 'Library/Application Support/orca/codex-accounts'
    if accounts.exists():
        paths.extend(accounts.glob('*/home/config.toml'))
    import tomllib
    for path in paths:
        original = path.read_text() if path.exists() else ''
        parsed = tomllib.loads(original)
        existing = parsed.get('mcp_servers', {})
        text = original
        for name, server in servers.items():
            if name in existing:
                if existing[name].get('command') == server['command'] and existing[name].get('args') == server['args']:
                    continue
                raise RuntimeError('Existing Codex MCP server differs: ' + name + '. Review ' + str(path) + ' before retrying.')
            text += '\n[mcp_servers.' + name + ']\ncommand = ' + json.dumps(server['command']) + '\nargs = ' + json.dumps(server['args']) + '\n'
        tomllib.loads(text)
        managed.write(path, text)
