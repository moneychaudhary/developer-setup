import json
import os
import pathlib
import pty
import select
import subprocess
import tempfile
import time
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]


class TerminalTests(unittest.TestCase):
    def run_prompt(self,key):
        with tempfile.TemporaryDirectory() as temp:
            master,slave=pty.openpty()
            process=subprocess.Popen([str(ROOT/'setup'),'install','--only','shell','--configure-only','--home',temp],stdin=slave,stdout=slave,stderr=slave)
            os.close(slave)
            output=b''
            try:
                deadline=time.monotonic()+5
                while b'[Enter]' not in output and time.monotonic()<deadline:
                    if select.select([master],[],[],.1)[0]:
                        output+=os.read(master,8192)
                self.assertIn(b'[Enter]',output)
                os.write(master,key)
                process.wait(timeout=5)
                self.assertEqual(process.returncode,0)
                checkpoint=pathlib.Path(temp)/'.local/state/developer-setup/checkpoint.json'
                return json.loads(checkpoint.read_text())['steps']['shell.configure']['status']
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                os.close(master)

    def test_enter_applies_configuration(self):
        self.assertEqual(self.run_prompt(b'\r'),'configured')

    def test_backspace_skips_configuration(self):
        self.assertEqual(self.run_prompt(b'\x7f'),'skipped')

    def test_forward_delete_skips_configuration(self):
        self.assertEqual(self.run_prompt(b'\x1b[3~'),'skipped')
