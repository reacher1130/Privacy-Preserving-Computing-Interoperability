#!/usr/bin/env python3
"""Export or verify/extract the source-only, credential-free native PaddleDTX snapshot."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'platform/thirdparty/paddledtx-source.tar.gz'
MANIFEST = ARCHIVE.with_name('paddledtx-source.json')
PARTS = {
    'dtx-manager': ('blockchain', 'cmd', 'config', 'controllers', 'handlers', 'models', 'pkg', 'routers', 'vendor', 'go.mod', 'go.sum', 'main.go'),
    'dtx-fe': ('scripts', 'src', 'package.json', 'package-lock.json', 'jsconfig.json', 'tsconfig.json', '.prettierrc.json'),
    'PaddleDTX': ('dai', 'xdb', 'crypto', 'LICENSE', 'NOTICE'),
}


def included(module, rel):
    p = Path(rel)
    if module not in PARTS or not p.parts:
        return False
    if p.is_absolute() or '..' in p.parts:
        return False
    if p.parts[0] not in PARTS[module]:
        return False
    if any(v in p.parts for v in ('.git', 'node_modules', '__pycache__')):
        return False
    if p.suffix.lower() in ('.key', '.pem', '.p12', '.pfx', '.log', '.zip', '.gz', '.tar', '.deb', '.exe', '.sqlite') or p.name == '.DS_Store':
        return False
    if '.sqlite' in p.name or p.name.endswith(('.mv.db', '.trace.db')) or p.name.startswith('.env'):
        return False
    if p.name.endswith('_test.go'):
        return False  # Historical tests embed deployment identities; current regression tests arrive through reviewed patches.
    if module == 'dtx-manager' and 'vendor' in p.parts and p.parts[0] != 'vendor':
        return False
    if module == 'PaddleDTX':
        # Keep Go config packages and dependency licenses; omit deployment identities and runtime fixtures.
        if len(p.parts) > 1 and p.parts[1] in ('conf', 'testdata', 'bin', 'deb', 'output', 'data', 'config-local-cli.toml'):
            return False
        if len(p.parts) > 1 and 'vendor' not in p.parts and p.suffix not in ('.go', '.mod', '.sum', '.proto', '.c', '.h', '.s', '.S') and p.name not in ('LICENSE', 'NOTICE'):
            return False
    return True


def sanitize(module, rel, data):
    if (module, rel) == ('dtx-manager', 'handlers/baas/baas.go'):
        # Retired deployment notes contained a real BaaS password hash.
        data = data.split('// 获取验证码\n//fetch'.encode())[0]
    if module == 'dtx-fe' and rel in ('scripts/webpack.dev.js', 'scripts/webpack.dev2.js'):
        text = data.decode()
        text = '\n'.join(line for line in text.splitlines() if not ('// target:' in line)) + '\n'
        data = re.sub(r"target: 'http://[^']+'", "target: 'http://127.0.0.1:18088'", text).encode()
    if (module, rel) == ('dtx-fe', 'src/views/Operation/Blockchain/index.tsx'):
        text = data.decode()
        first = text.index('  const openBass = useCallback(() => {')
        end = text.index('  return (', first)
        text = text[:first] + text[end:]
        first = text.index('        {\n          <Button')
        end = text.index('        <Row', first)
        text = text[:first] + text[end:]
        text = text.replace('useCallback, ', '').replace('  getJumpToken,\n', '').replace("import Button from '@/components/Button';\n", '')
        data = text.encode()
    return data


def snapshot(source):
    if ARCHIVE.exists() or MANIFEST.exists():
        raise RuntimeError('Snapshot already exists; retain it until deliberately replacing both archive and manifest')
    entries = []
    provenance = {}
    import subprocess
    for name in PARTS:
        base = source / name
        provenance[name] = subprocess.check_output(['git', '-C', str(base), 'rev-parse', 'HEAD'], text=True).strip()
        for path in sorted(base.rglob('*')):
            rel = str(path.relative_to(base))
            if path.is_file() and not path.is_symlink() and included(name, rel):
                entries.append((name + '/' + rel, sanitize(name, rel, path.read_bytes()), path.stat().st_mode & 0o111))
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVE.open('wb') as output, gzip.GzipFile(filename='', fileobj=output, mode='wb', mtime=0) as zipped, tarfile.open(fileobj=zipped, mode='w') as tar:
        for name, data, executable in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if executable else 0o644
            tar.addfile(info, io.BytesIO(data))
    record = {'format': 1, 'sha256': hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
              'source_commits': provenance, 'files': len(entries), 'source_bytes': sum(len(d) for _, d, _ in entries),
              'note': 'Build source snapshot includes local source changes. No original Git metadata, runtime configuration, identities, databases, logs or compiled artifacts. Historical identity tests and credential-bearing BaaS deployment comments omitted; obsolete external BaaS jump disabled and dev proxy targets localhost. Original licenses remain with source; the native frontend declares UNLICENSED.'}
    MANIFEST.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


def extract(destination):
    record = json.loads(MANIFEST.read_text())
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != record['sha256']:
        raise RuntimeError('Native source archive checksum mismatch')
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError('Extract into an empty build directory, not existing source or runtime state')
    with tarfile.open(ARCHIVE, 'r:gz') as tar:
        members = tar.getmembers()
        if len(members) != record['files'] or sum(member.size for member in members) != record['source_bytes'] or len({m.name for m in members}) != len(members):
            raise RuntimeError('Native source member count mismatch')
        for member in members:
            if not member.isfile() or member.name.startswith('/') or '..' in Path(member.name).parts or not included(Path(member.name).parts[0], str(Path(member.name).relative_to(Path(member.name).parts[0]))):
                raise RuntimeError('Unexpected source archive member: ' + member.name)
        destination.mkdir(parents=True, exist_ok=True)
        for member in members:
            path = destination / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(tar.extractfile(member).read())
            path.chmod(member.mode)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--snapshot', type=Path, help='Maintainer only: legacy collection directory, never a running deployment')
    group.add_argument('--extract', type=Path, help='Verify and extract into an empty disposable build directory')
    args = parser.parse_args()
    if args.snapshot:
        snapshot(args.snapshot)
    else:
        extract(args.extract)
