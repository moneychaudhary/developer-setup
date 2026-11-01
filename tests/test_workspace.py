import os
import pathlib
import plistlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from devsetup import workspace
from devsetup.config import ManagedFiles


def fake_run(calls):
    # Record commands and create the files that osacompile and iconutil would produce
    def run(args, capture=False):
        calls.append(args)
        if args[0] == 'osacompile':
            resources = pathlib.Path(args[2]) / 'Contents/Resources'
            resources.mkdir(parents=True)
            (resources / 'Assets.car').write_bytes(b'catalog')
            (pathlib.Path(args[2]) / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleName': 'applet', 'CFBundleIconName': 'applet'}))
        if args[0] == 'iconutil':
            pathlib.Path(args[-1]).write_bytes(b'icns')
        return ''
    return run


class WorkspaceTest(unittest.TestCase):
    def test_installs_executable_scripts_through_managed_files(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch('shutil.which', return_value=None):
            home = pathlib.Path(temp)
            managed = ManagedFiles(home, home / 'state')
            workspace.configure(home, managed, run=fake_run([]))
            script = home / '.local/share/workspace/signin.sh'
            self.assertTrue(os.access(script, os.X_OK))
            self.assertIn(str(script), managed.records)

    def test_builds_signed_apps_with_their_own_icon_and_name(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp, mock.patch('shutil.which', return_value='/usr/bin/tool'):
            home = pathlib.Path(temp)
            workspace.configure(home, ManagedFiles(home, home / 'state'), run=fake_run(calls))
            app = home / 'Applications/Workspace/SignIn.app'
            info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
            self.assertEqual(info['CFBundleName'], 'SignIn')
            self.assertNotIn('CFBundleIconName', info)
            self.assertFalse((app / 'Contents/Resources/Assets.car').exists())
            self.assertEqual((app / 'Contents/Resources/applet.icns').read_bytes(), b'icns')
            self.assertIn(['codesign', '--force', '--sign', '-', str(app)], calls)

    def test_desktop_shortcuts_skip_missing_apps_and_keep_existing_items(self):
        with tempfile.TemporaryDirectory() as temp:
            home = pathlib.Path(temp)
            (home / 'Applications/Workspace/SignIn.app').mkdir(parents=True)
            (home / 'Desktop').mkdir()
            (home / 'Desktop/SignOut').write_text('mine')
            (home / 'Applications/Workspace/SignOut.app').mkdir()
            made = workspace.desktop_shortcuts(home)
            self.assertIn('SignIn', made)
            self.assertNotIn('SignOut', made)
            self.assertEqual((home / 'Desktop/SignOut').read_text(), 'mine')
            self.assertEqual((home / 'Desktop/SignIn').resolve(), (home / 'Applications/Workspace/SignIn.app').resolve())


if __name__ == '__main__':
    unittest.main()
