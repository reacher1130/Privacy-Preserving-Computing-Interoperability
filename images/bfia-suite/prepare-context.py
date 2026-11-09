#!/usr/bin/env python3
"""Prepare a pinned-source image context for maintainers; end users pull the release image."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = {'__init__.py', 'run_python_tests.sh', 'run_cpp_tests.sh',
           'run_audited_cpp_tests.sh', 'generate_cpp_fixtures.py',
           'collect_protocol_audit.py', 'validate_numerics.py', 'validate_python_outputs.py'}


def selected(name):
    path = Path(name)
    if any(part in ('.git', '.cache', '__pycache__', 'results', '.local-backups') for part in path.parts):
        return False
    if name.startswith(('secretflow/', 'interconnection/interconnection/')):
        return path.suffix in ('.py', '.pyi', '.proto', '.json', '.txt')
    if name.startswith('bfia/'):
        relative = path.relative_to('bfia')
        return (len(relative.parts) == 1 and relative.name in SCRIPTS
                or len(relative.parts) == 2 and relative.parts[0] in ('sgb', 'he_woe') and path.suffix == '.py')
    return False


def prepare(source, output, rg):
    source, output, rg = Path(source).resolve(), Path(output).resolve(), Path(rg).resolve()
    if output.exists():
        raise RuntimeError('Use a new image context directory; existing files are never replaced')
    repo = source / 'platform/secretflow'
    revision = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    pin = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD:platform/secretflow'], text=True).strip()
    if revision != pin:
        raise RuntimeError('SecretFlow does not match the recorded source pin')
    binary = rg.read_bytes()
    if binary[:6] != b'\x7fELF\x02\x01' or int.from_bytes(binary[18:20], 'little') != 62:
        raise RuntimeError('Supply the reviewed Linux amd64 ripgrep binary from the build server')
    licenses = [rg.parent / name for name in ('LICENSE-MIT', 'UNLICENSE')]
    if not all(path.is_file() for path in licenses):
        raise RuntimeError('Keep ripgrep LICENSE-MIT and UNLICENSE beside its executable')
    rows = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '--stage', '-z'])
    entries = []
    for row in rows.split(b'\0'):
        if not row:
            continue
        metadata, raw_name = row.split(b'\t', 1)
        mode, oid, stage = metadata.decode().split()
        name = raw_name.decode()
        if selected(name) or name in ('LICENSE', 'interconnection/LICENSE'):
            if mode not in ('100644', '100755') or stage != '0':
                raise RuntimeError('Only unmerged-free regular tracked source files may enter the image')
            path = repo / name
            if path.is_symlink():
                raise RuntimeError('Image source cannot be replaced by a symbolic link: ' + name)
            data = path.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if actual != oid:
                raise RuntimeError('Uncommitted source change: ' + name)
            entries.append((name, mode, data))
    required = {'secretflow/__init__.py', 'secretflow/version.py', 'bfia/sgb/alice.py',
                'bfia/he_woe/bob.py', 'bfia/run_cpp_tests.sh', 'bfia/validate_numerics.py',
                'interconnection/interconnection/__init__.py', 'LICENSE', 'interconnection/LICENSE'}
    if not required <= {name for name, _, _ in entries}:
        raise RuntimeError('Incomplete BFIA source checkout')
    output.mkdir(parents=True)
    manifest = {'format': 1, 'secretflow_commit': revision, 'files': {},
                'ripgrep_sha256': hashlib.sha256(binary).hexdigest()}
    for name, mode, data in entries:
        destination = output / 'source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        destination.chmod(0o755 if mode == '100755' else 0o644)
        manifest['files'][name] = hashlib.sha256(data).hexdigest()
    for name in ('Dockerfile', 'entrypoint.py', 'ic-main.sh'):
        shutil.copyfile(source / 'images/bfia-suite' / name, output / name)
    (output / 'rg').write_bytes(binary)
    (output / 'licenses').mkdir()
    for path in licenses:
        shutil.copyfile(path, output / 'licenses' / ('ripgrep-' + path.name))
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--rg', required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.source, args.output, args.rg)
    print(json.dumps({'secretflow_commit': result['secretflow_commit'], 'source_files': len(result['files'])}))
