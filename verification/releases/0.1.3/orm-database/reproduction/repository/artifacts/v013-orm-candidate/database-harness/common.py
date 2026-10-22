"""Read-only binding and owned-path guards shared by the isolated runners."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parent
ROOT = CANDIDATE.parents[1]
EXPECTED_CANDIDATE_SHA = 'b5f7e88396931f0051f205cb845ff05c83224e622ea02ddf06115ab4b6fd38f5'

def binding(path):
    path = Path(path)
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for raw in iter(lambda: stream.read(65536), b''):
            digest.update(raw)
            size += len(raw)
    return {'sha256': digest.hexdigest(), 'bytes': size}

def under(path, parent):
    path, parent = Path(path).resolve(), Path(parent).resolve()
    if not path.is_relative_to(parent) or path == parent:
        raise ValueError('Use a fresh owned descendant of the isolated harness')
    return path

def inputs():
    candidate_path = CANDIDATE / 'candidate-manifest.json'
    if binding(candidate_path)['sha256'] != EXPECTED_CANDIDATE_SHA:
        raise ValueError('The reviewed ORM candidate manifest changed')
    manifest = json.loads(candidate_path.read_text(encoding='utf8'))
    result = {'candidate-manifest.json': binding(candidate_path)}
    for row in manifest['files']:
        path = under(CANDIDATE / row['path'], CANDIDATE)
        actual = binding(path)
        if actual != {key: row[key] for key in ('sha256', 'bytes')}:
            raise ValueError('Frozen ORM candidate file changed: ' + row['path'])
        result['candidate/' + row['path']] = actual
    harness = json.loads((HERE / 'execution-inputs.json').read_text(encoding='utf8'))
    for row in harness['files']:
        path = under(HERE / row['path'], HERE)
        actual = binding(path)
        if actual != {key: row[key] for key in ('sha256', 'bytes')}:
            raise ValueError('Frozen harness file changed: ' + row['path'])
        result['harness/' + row['path']] = actual
    result['execution-inputs.json'] = binding(HERE / 'execution-inputs.json')
    return result

def connection_config(run_root, filename):
    run_root = under(run_root, HERE / 'executions')
    path = Path(filename).resolve()
    if path != run_root / 'private/connection.json':
        raise ValueError('Only this owned run connection file is accepted')
    config = json.loads(path.read_text(encoding='utf8'))
    if (set(config) != {'host', 'port', 'dbname', 'user', 'password'}
            or config['host'] != '127.0.0.1' or config['dbname'] != 'postgres' or config['user'] != 'mtw'
            or type(config['port']) is not int or not 1 <= config['port'] <= 65535
            or type(config['password']) is not str or len(config['password']) != 48
            or any(c not in '0123456789abcdef' for c in config['password'])):
        raise ValueError('Expected the isolated owned-loopback PostgreSQL configuration')
    return {'connect_timeout': 5, 'options': '-c statement_timeout=10000 -c lock_timeout=5000', **config}
