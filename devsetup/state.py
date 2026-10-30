import datetime
import json
import os
import uuid
import shlex


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.chmod(0o600)
    os.replace(temp, path)


class State:
    def __init__(self, root, command, resume=False):
        self.root = root
        self.path = root / 'checkpoint.json'
        if resume:
            if not self.path.exists():
                raise RuntimeError('No previous run to resume.')
            self.data = json.loads(self.path.read_text())
            if self.data['command'] != command:
                raise RuntimeError('Resume the original command: ' + self.data['command'])
        else:
            self.data = {'run_id': str(uuid.uuid4()), 'command': command, 'steps': {}, 'selection': [], 'finished': False}
        self.save()

    def save(self):
        self.data['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        atomic_json(self.path, self.data)

    def mark(self, step, status, version='', detail=''):
        self.data['steps'][step] = {'status': status, 'version': version, 'detail': detail}
        self.save()

    def report(self):
        target = self.root / 'reports' / (self.data['run_id'] + '.json')
        atomic_json(target, self.data)
        print('\nFinal status report')
        for step, value in self.data['steps'].items():
            print(f"  {step:32} {value['status']:18} {value['version']}")
            if value['detail']:
                print('    ' + value['detail'])
        print('Report:', target)
        if not self.data['finished'] or any(v['status'] in ('failed', 'pending', 'interrupted') for v in self.data['steps'].values()):
            print('Resume: ./setup ' + self.data['command'] + ' --resume --home ' + shlex.quote(str(self.root.parents[2])))
        return target
