import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from devsetup import providers
from devsetup.doctor import mcp_handshake


class ProviderTests(unittest.TestCase):
    def test_package_install_uses_selected_runtime(self):
        with patch('devsetup.providers.run') as run, patch('devsetup.providers.tool_version',return_value='installed'):
            providers.install({'provider':'npm','package':'@blackwell-systems/agent-lsp'})
        self.assertEqual(run.call_args.args[0],['npm','install','--global','@blackwell-systems/agent-lsp@latest'])

    def test_runtime_falls_back_for_os_error_only(self):
        with patch('devsetup.providers.available',return_value='/bin/mise'), patch('devsetup.providers.run') as run, patch('devsetup.providers.subprocess.run') as install:
            run.side_effect=['30.0.0\n30.0.1\n31.0.0','']
            install.side_effect=[subprocess.CompletedProcess([],1,'','unsupported macOS'),subprocess.CompletedProcess([],0,'','')]
            version=providers.install({'provider':'mise','package':'node'})
            self.assertIn('30.0.1',version)
            self.assertEqual(install.call_args.args[0],['mise','install','node@30.0.1'])

    def test_network_failure_does_not_select_old_runtime(self):
        with patch('devsetup.providers.available',return_value='/bin/mise'), patch('devsetup.providers.run',return_value='31.0.0\n30.0.0'), patch('devsetup.providers.subprocess.run') as install:
            install.return_value=subprocess.CompletedProcess([],1,'','network timeout')
            with self.assertRaisesRegex(RuntimeError,'no downgrade'):
                providers.install({'provider':'mise','package':'node'})
            self.assertEqual(install.call_count,1)

    def test_mcp_doctor_requires_initialize_and_tools_result(self):
        import sys
        script = "import sys,json\nfor line in sys.stdin:\n r=json.loads(line)\n if r.get('method')=='initialize': print(json.dumps({'id':r['id'],'result':{'protocolVersion':'2024-11-05'}}),flush=True)\n if r.get('method')=='tools/list': print(json.dumps({'id':r['id'],'result':{'tools':[{'name':'one'}]}}),flush=True)"
        self.assertEqual(mcp_handshake({'command':sys.executable,'args':['-u','-c',script]}),(True,1))
