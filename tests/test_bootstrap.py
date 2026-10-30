import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def test_clones_both_repositories_and_preserves_dirty_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            base=pathlib.Path(temp)
            sources=base/'sources'
            sources.mkdir()
            for name in ('developer-setup','developer-skills'):
                repo=sources/name
                subprocess.run(['git','init','-b','main',str(repo)],check=True,capture_output=True)
                (repo/'sample.txt').write_text('original\n')
                subprocess.run(['git','-C',str(repo),'add','sample.txt'],check=True)
                subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','Initial fixture'],check=True,capture_output=True)
            env=dict(os.environ,DEVELOPER_SETUP_SOURCE_ROOT=str(sources))
            destination=base/'projects with spaces'
            command=['bash',str(ROOT/'bootstrap.sh'),'--clone-only','--projects-dir',str(destination)]
            first=subprocess.run(command,env=env,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertTrue((destination/'developer-skills/.git').is_dir())
            edited=destination/'developer-setup/sample.txt'
            edited.write_text('local changes\n')
            second=subprocess.run(command,env=env,capture_output=True,text=True)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertEqual(edited.read_text(),'local changes\n')

    def test_refuses_to_replace_nonrepository_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            path=pathlib.Path(temp)
            (path/'developer-setup').mkdir()
            result=subprocess.run(['bash',str(ROOT/'bootstrap.sh'),'--clone-only','--projects-dir',temp],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Refusing to replace',result.stderr)
