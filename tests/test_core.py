import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class CoreTests(unittest.TestCase):
    def test_dry_run_does_not_write_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            result = subprocess.run([str(ROOT / "setup"), "install", "--all", "--dry-run", "--home", tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("claude_code", result.stdout)
            self.assertIn("localstack", result.stdout)
            self.assertEqual(list(home.iterdir()), [])

    def test_no_tty_requires_explicit_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([str(ROOT / "setup"), "install", "--home", tmp], input="", capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("interactive", result.stderr.lower())

    def test_resume_keeps_completed_step(self):
        sys.path.insert(0, str(ROOT))
        from devsetup.state import State
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            a = State(path, "install")
            a.mark("git.install", "installed", "2.0")
            b = State(path, "install", resume=True)
            self.assertEqual(b.data["steps"]["git.install"]["status"], "installed")
            self.assertEqual(a.data["run_id"], b.data["run_id"])

    def test_configuration_preserves_unmanaged_keys_and_rolls_back(self):
        sys.path.insert(0, str(ROOT))
        from devsetup.config import ManagedFiles
        with tempfile.TemporaryDirectory() as tmp:
            h = pathlib.Path(tmp)
            target = h / "settings.json"
            target.write_text('{"unrelated": true, "font": "old"}')
            files = ManagedFiles(h, h / "state")
            files.merge_json(target, {"font": "new"})
            self.assertEqual(json.loads(target.read_text()), {"unrelated": True, "font": "new"})
            target.write_text('{"unrelated": true, "font": "edited"}')
            self.assertEqual(files.rollback(), [str(target)])
            self.assertEqual(json.loads(target.read_text())["font"], "edited")

    def test_compatible_release_selection(self):
        sys.path.insert(0, str(ROOT))
        from devsetup.providers import newest_compatible
        releases = [
            {"version": "3.0", "min_os": "15.0", "arch": ["arm64"]},
            {"version": "2.1", "min_os": "13.0", "arch": ["arm64", "x86_64"]},
            {"version": "4.0-beta", "min_os": "12.0", "arch": ["arm64"], "prerelease": True},
        ]
        self.assertEqual(newest_compatible(releases, "14.0", "arm64")["version"], "2.1")

    def test_enter_delete_controls(self):
        sys.path.insert(0, str(ROOT))
        from devsetup.ui import key_decision
        self.assertTrue(key_decision("\r"))
        self.assertFalse(key_decision("\x7f"))
        self.assertFalse(key_decision("\x08"))
        self.assertIsNone(key_decision("x"))

if __name__ == "__main__":
    unittest.main()

class IsolationTests(unittest.TestCase):
    def test_alternate_home_rejects_login(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run([str(ROOT/'setup'), 'login', '--only', 'github', '--home', temp], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('alternate', result.stderr)
            self.assertEqual(list(pathlib.Path(temp).iterdir()), [])

    def test_capture_dry_run_has_no_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = pathlib.Path(temp)/'capture'
            result = subprocess.run([str(ROOT/'setup'), 'capture', '--dry-run', '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(output.exists())

    def test_configuration_only_and_resume_in_isolated_home(self):
        with tempfile.TemporaryDirectory() as temp:
            args = [str(ROOT/'setup'), 'install', '--only', 'vscode,shell,git_config', '--home', temp, '--configure-only', '--yes']
            first = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            checkpoint = pathlib.Path(temp)/'.local/state/developer-setup/checkpoint.json'
            run_id = json.loads(checkpoint.read_text())['run_id']
            second = subprocess.run(args+['--resume'], capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(checkpoint.read_text())['run_id'], run_id)
            self.assertIn('keeping completed', second.stdout)

class RegressionTests(unittest.TestCase):
    def test_jsonc_settings_keep_urls_strings_and_unrelated_keys(self):
        sys.path.insert(0, str(ROOT))
        from devsetup.config import ManagedFiles
        with tempfile.TemporaryDirectory() as temp:
            home = pathlib.Path(temp)
            target = home/'settings.json'
            target.write_text('{// comment\n"url":"https://example.test/a,}", /* note */ "array":[1,],}')
            ManagedFiles(home, home/'state').merge_json(target, {'font':'SF Mono'})
            parsed = json.loads(target.read_text())
            self.assertEqual(parsed['url'], 'https://example.test/a,}')
            self.assertEqual(parsed['array'], [1])

    def test_resume_remembers_configuration_only_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            args = [str(ROOT/'setup'), 'install', '--only', 'vscode', '--home', temp, '--configure-only', '--no-extensions', '--yes']
            self.assertEqual(subprocess.run(args,capture_output=True).returncode, 0)
            second = subprocess.run([str(ROOT/'setup'), 'install', '--resume', '--home', temp],capture_output=True,text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            data=json.loads((pathlib.Path(temp)/'.local/state/developer-setup/checkpoint.json').read_text())
            self.assertNotIn('vscode.install',data['steps'])
            self.assertTrue(data['options']['configure_only'])

    def test_orca_export_drops_account_and_project_state(self):
        sys.path.insert(0, str(ROOT))
        from devsetup.config import portable_orca
        result = portable_orca({'theme':'dark', 'claudeManagedAccounts':[{'token':'fake'}], 'workspaceDir':'/private/project', 'sourceControlAi':{'agentId':'private-id','actions':{'commitMessage':{'commandInputTemplate':'short','agentId':'private'}}}})
        self.assertEqual(result, {'theme':'dark','sourceControlAi':{'actions':{'commitMessage':{'commandInputTemplate':'short'}}}})

class OwnershipTests(unittest.TestCase):
    def test_reinstall_refuses_to_replace_locally_modified_owned_file(self):
        sys.path.insert(0,str(ROOT))
        from devsetup.config import ManagedFiles
        with tempfile.TemporaryDirectory() as temp:
            home=pathlib.Path(temp)
            target=home/'settings.json'
            target.write_text('{"unrelated":"original"}')
            manager=ManagedFiles(home,home/'state')
            manager.merge_json(target,{'font':'first'})
            target.write_text('{"unrelated":"user edit","font":"first"}')
            with self.assertRaisesRegex(RuntimeError,'locally modified'):
                manager.merge_json(target,{'font':'second'})
            self.assertEqual(json.loads(target.read_text())['unrelated'],'user edit')
