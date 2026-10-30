import hashlib
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from devsetup.config import configure_orca


class OrcaTests(unittest.TestCase):
    def make_db(self, home):
        path = home/'Library/Application Support/orca/profiles/local-default/profile-state.db'
        path.parent.mkdir(parents=True)
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE profile_state_documents(domain TEXT PRIMARY KEY, payload TEXT, domain_version INTEGER, revision INTEGER, updated_at INTEGER, content_hash TEXT)')
        db.execute('CREATE TABLE profile_state_meta(key TEXT PRIMARY KEY,value TEXT)')
        for name, value in [('settings', {'theme':'old','privateAccountField':'preserve'}),('repos',[{'path':'/private/project'}])]:
            payload=json.dumps(value)
            db.execute('INSERT INTO profile_state_documents VALUES(?,?,1,1,0,?)',(name,payload,hashlib.sha256(payload.encode()).hexdigest()))
        db.execute("INSERT INTO profile_state_meta VALUES('revision','1')")
        db.commit()
        db.close()
        return path

    def test_offline_restore_preserves_unmanaged_settings_and_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            home=pathlib.Path(temp)
            path=self.make_db(home)
            with patch('devsetup.config.subprocess.run') as ps, patch('devsetup.config.platform',create=True):
                ps.return_value.stdout=''
                with patch('platform.system',return_value='Darwin'):
                    backup=configure_orca(home,home/'state')
            self.assertTrue(pathlib.Path(backup).exists())
            db=sqlite3.connect(path)
            settings=json.loads(db.execute("SELECT payload FROM profile_state_documents WHERE domain='settings'").fetchone()[0])
            self.assertEqual(settings['privateAccountField'],'preserve')
            self.assertEqual(json.loads(db.execute("SELECT payload FROM profile_state_documents WHERE domain='repos'").fetchone()[0]),[{'path':'/private/project'}])
            self.assertEqual(db.execute("SELECT value FROM profile_state_meta WHERE key='revision'").fetchone()[0],'2')
            payload,checksum=db.execute("SELECT payload,content_hash FROM profile_state_documents WHERE domain='settings'").fetchone()
            self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(),checksum)
            db.close()

    def test_running_orca_blocks_database_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            home=pathlib.Path(temp)
            path=self.make_db(home)
            before=path.read_bytes()
            with patch('devsetup.config.subprocess.run') as ps:
                ps.return_value.stdout='/Applications/Orca.app/Contents/MacOS/Orca'
                with self.assertRaisesRegex(RuntimeError,'Close Orca'):
                    configure_orca(home,home/'state')
            self.assertEqual(before,path.read_bytes())
