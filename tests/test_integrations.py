import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from devsetup.config import ManagedFiles
from devsetup.integrations import configure


class IntegrationTests(unittest.TestCase):
    def test_skill_seekers_uses_installed_interpreter_without_ephemeral_download(self):
        with tempfile.TemporaryDirectory() as temp:
            home=pathlib.Path(temp)
            tool_root=home/'tools'
            python=tool_root/'skill-seekers/bin/python'
            python.parent.mkdir(parents=True)
            python.touch()
            with patch('devsetup.integrations.shutil.which',side_effect=lambda name:'/bin/'+name),patch('subprocess.run') as command:
                command.return_value.stdout=str(tool_root)+'\n'
                configure(home,ManagedFiles(home,home/'state'))
            settings=json.loads((home/'.cursor/mcp.json').read_text())
            server=settings['mcpServers']['skill-seekers']
            self.assertEqual(server['command'],str(python))
            self.assertEqual(server['args'],['-m','skill_seekers.mcp.server_fastmcp'])
            self.assertNotIn('--from',server['args'])
