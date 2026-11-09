#!/usr/bin/env python3
"""Run the fixed public BFIA suite without a Docker daemon or host source checkout."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tarfile

SOURCE = Path('/opt/bfia/secretflow')
PYTHON = ('sgb', 'he_woe')
CPP = ('ecdh-psi', 'ss-lr', 'ss-xgb', 'ss-pearson', 'ss-vif', 'ss-compare')
MAX_COMPRESSED = 8 * 1024 * 1024
MAX_UNCOMPRESSED = 64 * 1024 * 1024
MAX_MEMBERS = 1024


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kuscia', action='store_true')
    parser.add_argument('run_id', nargs='?', default=os.environ.get('BFIA_RUN_ID'))
    args = parser.parse_args(argv)
    if not args.run_id or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.run_id):
        parser.error('Supply a lowercase UUID as run ID or BFIA_RUN_ID')
    return args


def output_directory(value, run_id):
    output = Path(value)
    if not output.is_absolute() or output == Path('/') or '..' in output.parts:
        raise ValueError('The result directory must be an absolute, non-root private directory')
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError('The result directory cannot have symbolic-link components')
    if any((output / name).exists() or (output / name).is_symlink()
           for name in ('exit-code', 'report.json', 'python/' + run_id, 'cpp/' + run_id)):
        raise ValueError('Refusing to reuse an existing suite result')
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    return output


def write_atomic(path, content):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('xb') as stream:
        stream.write(content)
    temporary.replace(path)


def frames(kind, run_id, payload, relative=None):
    prefix = run_id + (' ' + relative if relative else '')
    print(f'PPCI_BFIA_{kind}_BEGIN {prefix} {hashlib.sha256(payload).hexdigest()} {len(payload)}', flush=True)
    encoded = base64.b64encode(payload).decode('ascii')
    for start in range(0, len(encoded), 4096):
        print(f'PPCI_BFIA_{kind}_DATA {encoded[start:start + 4096]}', flush=True)
    print(f'PPCI_BFIA_{kind}_END {prefix}', flush=True)


def snapshots(output, run_id, sent):
    paths = []
    for language, algorithms, suffix in (('python', PYTHON, '.stdout.log'), ('cpp', CPP, '.log')):
        base = Path(language) / run_id
        paths.extend(base / algorithm / (party + suffix) for algorithm in algorithms for party in ('alice', 'bob'))
        paths.extend(base / name for name in ('numerical-validation.json', 'protocol-validation.json'))
    for relative in paths:
        path = output / relative
        if not path.is_file() or path.is_symlink():
            continue
        limit = 256 * 1024 if path.suffix == '.json' else 64 * 1024
        if path.suffix == '.json' and path.stat().st_size > limit:
            continue
        with path.open('rb') as stream:
            if path.suffix != '.json':
                stream.seek(max(0, path.stat().st_size - limit))
            payload = stream.read(limit)
        if path.suffix == '.json':
            try:
                json.loads(payload)
            except (ValueError, UnicodeError):
                continue
        checksum = hashlib.sha256(payload).hexdigest()
        if sent.get(str(relative)) != checksum:
            frames('FILE', run_id, payload, str(relative))
            sent[str(relative)] = checksum


def run_group(language, script, output, run_id, kuscia, sent):
    directory = output / language / run_id
    directory.mkdir(mode=0o700, parents=True)
    environment = {key: os.environ[key] for key in ('PATH', 'HOME', 'LANG', 'LD_LIBRARY_PATH', 'PYTHONHOME') if key in os.environ}
    environment.update(BFIA_RUN_ID=run_id, BFIA_RESULT_ROOT=str(output),
                       BFIA_PYTHON_ALICE_IP='127.0.0.1', BFIA_PYTHON_BOB_IP='127.0.0.2',
                       BFIA_CPP_RUNTIME='binary', BFIA_CPP_ALGOS=','.join(CPP),
                       BFIA_CPP_IMAGE='embedded-in-bfia-suite',
                       BFIA_TIMEOUT_SEC='120', BFIA_CPP_TIMEOUT_SEC='55',
                       PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    print('PPCI_BFIA_STAGE ' + run_id + ' ' + language, flush=True)
    with (directory / 'runner.log').open('wb') as log:
        process = subprocess.Popen(['bash', str(SOURCE / 'bfia' / script)], env=environment,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                if kuscia:
                    snapshots(output, run_id, sent)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            if kuscia:
                snapshots(output, run_id, sent)
            return process.returncode
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


def report(output, run_id, exits):
    algorithms = []
    for language, names in (('python', PYTHON), ('cpp', CPP)):
        checks = {}
        for kind in ('numerical', 'protocol'):
            try:
                value = json.loads((output / language / run_id / (kind + '-validation.json')).read_text())
                checks[kind] = value if isinstance(value, dict) else {}
            except (OSError, ValueError, UnicodeError):
                checks[kind] = {}
        for name in names:
            numerical = checks['numerical'].get(name, {})
            protocol = checks['protocol'].get(name, {})
            numerical = numerical if isinstance(numerical, dict) else {}
            protocol = protocol if isinstance(protocol, dict) else {}
            passed = numerical.get('pass') is True and protocol.get('pass') is True
            algorithms.append({'id': name, 'status': 'PASSED' if passed else 'FAILED',
                               'numerical': numerical, 'protocol': protocol})
    passed = all(value == 0 for value in exits.values()) and len(exits) == 2 and all(item['status'] == 'PASSED' for item in algorithms)
    result = {'runId': run_id, 'status': 'PASSED' if passed else 'FAILED',
              'algorithms': algorithms, 'exitCodes': exits}
    write_atomic(output / 'report.json', (json.dumps(result, indent=2) + '\n').encode())
    write_atomic(output / 'exit-code', b'0\n' if passed else b'1\n')
    return result


def bundle(output, run_id):
    files = [output / 'report.json', output / 'exit-code']
    for language in ('python', 'cpp'):
        for path in sorted((output / language / run_id).rglob('*')):
            if path.suffix in ('.json', '.jsonl', '.csv', '.log', '.txt', '.md'):
                files.append(path)
    members = []
    total = 0
    for path in files:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        relative = path.relative_to(output)
        if any(parent.is_symlink() for parent in path.parents if parent != output):
            raise ValueError('Artifact has a symbolic-link parent')
        total += info.st_size
        members.append((path, str(relative)))
    if len(members) > MAX_MEMBERS or total > MAX_UNCOMPRESSED:
        raise ValueError('Suite artifacts exceed the transport limit')
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz', dereference=False) as archive:
        for path, relative in members:
            archive.add(path, arcname=relative, recursive=False)
    payload = stream.getvalue()
    if len(payload) > MAX_COMPRESSED:
        raise ValueError('Compressed suite artifacts exceed the transport limit')
    return payload


def main(argv=None):
    args = arguments(argv)
    os.umask(0o077)
    default = '/tmp/bfia-suite.' + args.run_id if args.kuscia else '/results'
    output = output_directory(os.environ.get('BFIA_RESULT_ROOT', default), args.run_id)
    exits = {}
    sent = {}
    def stopped(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stopped)
    try:
        for language, script in (('python', 'run_python_tests.sh'), ('cpp', 'run_audited_cpp_tests.sh')):
            exits[language] = run_group(language, script, output, args.run_id, args.kuscia, sent)
    finally:
        result = report(output, args.run_id, exits)
        if args.kuscia:
            frames('BUNDLE', args.run_id, bundle(output, args.run_id))
    print(json.dumps(result), flush=True)
    return 0 if result['status'] == 'PASSED' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print('BFIA suite failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
