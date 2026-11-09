#!/usr/bin/env python3
"""Deploy, run, and package the complete isolated PPCI demo. No runtime data in releases."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
TOOLS = Path('/opt/ppci-tools')
BUILD = Path(os.environ.get('PPCI_BUILD_ROOT', '/opt/ppci-build'))
ARTIFACTS = ('secretpad/target/secretpad.jar', 'secretpad-kimi-upstream/target/secretpad.jar',
             'secretpad-frontend/apps/platform/dist', 'paddle', 'paddle-native/bin',
             'paddle-native/built.json', 'paddle-native/source.json')


def run(*args, **kw):
    print('+ ' + ' '.join(map(str, args)), flush=True)
    return subprocess.run([str(x) for x in args], check=True, **kw)


def digest(path, algorithm='sha256'):
    result = hashlib.new(algorithm)
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def unpack(archive, destination, allow_links=False):
    """Validate all members before touching disk, including older Python tar readers."""
    destination = Path(destination).resolve()
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or member.isdev() or member.isfifo():
                raise ValueError('Unsafe archive member: ' + member.name)
            target = destination / member.name
            if not target.resolve().is_relative_to(destination):
                raise ValueError('Archive escapes destination: ' + member.name)
            if member.issym() or member.islnk():
                link = PurePosixPath(member.linkname)
                resolved = (target.parent / member.linkname).resolve() if member.issym() else (destination / member.linkname).resolve()
                if not allow_links or link.is_absolute() or not resolved.is_relative_to(destination):
                    raise ValueError('Unsafe archive link: ' + member.name)
        stream.extractall(destination, filter='data') if sys.version_info >= (3, 12) else stream.extractall(destination)


def fetch(url, destination, expected, algorithm='sha256'):
    destination = Path(destination)
    if destination.is_file() and digest(destination, algorithm) == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.part')
    run('curl', '--fail', '--location', '--retry', '2', '--retry-all-errors',
        '--connect-timeout', '15', '--max-time', '900', '--user-agent', 'ppci-deploy/1.0',
        '--output', temporary, url)
    if digest(temporary, algorithm) != expected:
        temporary.unlink()
        raise RuntimeError('Download checksum mismatch: ' + url)
    temporary.replace(destination)


def url_text(url):
    return subprocess.check_output(['curl', '--fail', '--silent', '--show-error', '--location',
        '--retry', '2', '--retry-all-errors', '--connect-timeout', '15', '--max-time', '60',
        '--user-agent', 'ppci-deploy/1.0', '--header', 'Accept: application/json,text/plain,*/*', url], text=True)


def install_tools():
    if platform.machine() not in ('x86_64', 'amd64'):
        raise RuntimeError('Install native build tools inside the amd64 VM.')
    TOOLS.mkdir(parents=True, exist_ok=True)
    cache = TOOLS / 'downloads'
    cache.mkdir(exist_ok=True)
    # These tool versions match the project build; do not replace system toolchains.
    items = []
    go_name = 'go1.24.13.linux-amd64.tar.gz'
    # Official go.dev/dl JSON publishes this digest; .tar.gz.sha256 returns HTML.
    items.append(('https://go.dev/dl/' + go_name, '1fc94b57134d51669c72173ad5d49fd62afb0f1db9bf3f798fd98ee423f8d730', 'sha256', 'go124', 'go'))
    node_name = 'node-v22.14.0-linux-x64.tar.xz'
    sums = url_text('https://nodejs.org/dist/v22.14.0/SHASUMS256.txt')
    node_sha = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == node_name)
    items.append(('https://nodejs.org/dist/v22.14.0/' + node_name, node_sha, 'sha256', 'node20', 'node-v22.14.0-linux-x64'))
    mvn_name = 'apache-maven-3.9.9-bin.tar.gz'
    mvn_url = 'https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/' + mvn_name
    items.append((mvn_url, url_text(mvn_url + '.sha512').split()[0], 'sha512', 'maven', 'apache-maven-3.9.9'))
    assets = json.loads(url_text('https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse'))
    jdk = assets[0]['binary']['package']
    items.append((jdk['link'], jdk['checksum'], 'sha256', 'jdk21', None))
    for url, checksum, algorithm, target_name, prefix in items:
        target = TOOLS / target_name
        marker = target / '.ppci-checksum'
        if marker.is_file():
            continue
        if target.exists():
            raise RuntimeError('Refusing to overwrite existing unmanaged tool: ' + str(target))
        archive = cache / url.rsplit('/', 1)[-1]
        fetch(url, archive, checksum, algorithm)
        with tempfile.TemporaryDirectory(dir=TOOLS) as stage:
            unpack(archive, stage, allow_links=True)
            roots = list(Path(stage).iterdir())
            content = Path(stage) / prefix if prefix else roots[0]
            content.rename(target)
        marker.write_text(checksum + '\n')
    bazel = BUILD / 'tools/bazel-6.5.0'
    fetch('https://github.com/bazelbuild/bazel/releases/download/6.5.0/bazel-6.5.0-linux-x86_64', bazel,
          'a40ac69263440761199fcb8da47ad4e3f328cbe79ffbf4ecc14e5ba252857307')
    bazel.chmod(0o755)
    env = environment()
    if not (TOOLS / 'pnpm8/node_modules/.bin/pnpm').exists():
        run(TOOLS / 'node20/bin/npm', 'install', '--prefix', TOOLS / 'pnpm8', 'pnpm@8.8.0', env=env)
    if not (TOOLS / 'rg/rg').is_file():
        name = 'ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz'
        url = 'https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/' + name
        checksum = url_text(url + '.sha256').split()[0]
        fetch(url, cache / name, checksum)
        (TOOLS / 'rg').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as stage:
            unpack(cache / name, stage)
            shutil.copy2(Path(stage) / name.removesuffix('.tar.gz') / 'rg', TOOLS / 'rg/rg')


def environment():
    env = dict(os.environ, PPCI_SOURCE_ROOT=str(SOURCE), PPCI_BUILD_ROOT=str(BUILD))
    if (TOOLS / 'jdk21/bin/java').is_file():
        env['JAVA_HOME'] = str(TOOLS / 'jdk21')
    elif 'JAVA_HOME' not in env and shutil.which('java'):
        env['JAVA_HOME'] = str(Path(shutil.which('java')).resolve().parents[1])
    dirs = [TOOLS / p for p in ('node20/bin', 'maven/bin', 'go124/bin', 'pnpm8/node_modules/.bin', 'rg')]
    if env.get('JAVA_HOME'):
        dirs.insert(0, Path(env['JAVA_HOME']) / 'bin')
    env['PATH'] = ':'.join(map(str, dirs)) + ':' + env.get('PATH', '')
    return env


def source_files(root=None):
    """Only tracked working files and pinned recursive submodules enter a source export."""
    root = root or SOURCE
    if not (root / '.git').exists():
        marker = json.loads((root / '.ppci-source.json').read_text())
        for name, expected in marker['files'].items():
            path = root / name
            if path.is_symlink():
                actual = hashlib.sha256(os.readlink(path).encode()).hexdigest()
            else:
                actual = digest(path)
            if actual != expected:
                raise RuntimeError('Exported source changed: ' + name)
            yield path, name
        return
    def walk(repo, prefix=''):
        data = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '--stage', '-z'])
        for line in data.decode().split('\0'):
            if not line:
                continue
            meta, name = line.split('\t', 1)
            path = repo / name
            relative = prefix + name
            if meta.split()[0] == '160000':
                if not (path / '.git').exists():
                    raise RuntimeError('Uninitialized submodule: ' + relative)
                yield from walk(path, relative + '/')
            elif path.is_file() or path.is_symlink():
                yield path, relative
            else:
                raise RuntimeError('Tracked source missing: ' + relative)
    yield from walk(root)


def source_package(output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise RuntimeError('Output already exists: ' + str(output))
    manifest = {'format': 1, 'runtime_data_included': False, 'files': {}, 'excluded_external_links': []}
    if (SOURCE / '.git').exists():
        manifest['revision'] = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
        manifest['dirty'] = bool(subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain']))
    with tarfile.open(output, 'w:gz') as archive:
        for path, relative in source_files():
            if path.is_symlink() and (Path(os.readlink(path)).is_absolute() or not path.resolve().is_relative_to(SOURCE)):
                manifest['excluded_external_links'].append(relative)
                continue
            if path.resolve() == output:
                raise RuntimeError('Cannot include source export inside itself')
            manifest['files'][relative] = hashlib.sha256(os.readlink(path).encode()).hexdigest() if path.is_symlink() else digest(path)
            archive.add(path, arcname='ppci-source/' + relative, recursive=False)
        import io
        content = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo('ppci-source/.ppci-source.json')
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return manifest


def package(args):
    if args.source_only:
        target = Path(args.output or str(SOURCE / 'dist/ppci-source.tar.gz'))
        source_package(target)
        target.with_name(target.name + '.sha256').write_text(digest(target) + '  ' + target.name + '\n')
        print(target.resolve())
        return
    target = Path(args.output or str(SOURCE / 'dist' / time.strftime('%Y%m%d-%H%M%S'))).resolve()
    target.mkdir(parents=True, exist_ok=False)
    source_package(target / 'source.tar.gz')
    manifest = {'format': 1, 'platform': 'linux/amd64', 'runtime_data_included': False, 'sha256': {}}
    files = [BUILD / name for name in ARTIFACTS]
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        raise RuntimeError('Build complete stack before release packaging; missing: ' + ', '.join(missing))
    with tarfile.open(target / 'artifacts.tar.gz', 'w:gz') as archive:
        for name in ARTIFACTS:
            archive.add(BUILD / name, arcname=name)
    if (TOOLS / 'jdk21/bin/java').is_file():
        with tarfile.open(target / 'tools.tar.gz', 'w:gz') as archive:
            for name in ('jdk21', 'rg'):
                archive.add(TOOLS / name, arcname=name)
    if args.with_images:
        images = json.loads((BUILD / 'release-images.json').read_text())
        if not images:
            raise RuntimeError('No complete release image inventory')
        manifest['images'] = []
        for tag in images:
            item = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag]))[0]
            if item['Architecture'] != 'amd64':
                raise RuntimeError('Wrong release image architecture: ' + tag)
            manifest['images'].append({'tag': tag, 'id': item['Id']})
        with (target / 'images.tar.gz').open('wb') as out:
            save = subprocess.Popen(['docker', 'save', *images], stdout=subprocess.PIPE)
            compressor = subprocess.Popen(['gzip', '-1'], stdin=save.stdout, stdout=out)
            save.stdout.close()
            compressed = compressor.wait()
            saved = save.wait()
            if compressed or saved:
                raise RuntimeError('Docker image export failed')
    manifest['sha256'] = {p.name: digest(p) for p in target.iterdir() if p.is_file()}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (target / 'SHA256SUMS').write_text(''.join(f'{sha}  {name}\n' for name, sha in manifest['sha256'].items()))
    print(target)


def restore(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('format') != 1 or manifest.get('platform') != 'linux/amd64':
        raise RuntimeError('Unsupported release format/platform')
    required = {'source.tar.gz', 'artifacts.tar.gz', 'images.tar.gz'}
    if not required.issubset(manifest.get('sha256', {})):
        raise RuntimeError('Release checksum inventory is incomplete')
    if set(manifest['sha256']) - required - {'tools.tar.gz'}:
        raise RuntimeError('Unexpected release file inventory')
    for name, expected in manifest['sha256'].items():
        if Path(name).name != name or digest(directory / name) != expected:
            raise RuntimeError('Release checksum mismatch: ' + name)
    if not (directory / 'images.tar.gz').is_file():
        raise RuntimeError('Offline deployment requires package --with-images')
    BUILD.mkdir(parents=True, exist_ok=True)
    unpack(directory / 'artifacts.tar.gz', BUILD)
    if 'tools.tar.gz' in manifest['sha256']:
        # A target may already have host-managed tools; never replace them silently.
        TOOLS.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TOOLS) as temporary:
            unpack(directory / 'tools.tar.gz', temporary, allow_links=True)
            for path in Path(temporary).iterdir():
                dest = TOOLS / path.name
                if not dest.exists():
                    path.rename(dest)
    run('docker', 'load', '-i', directory / 'images.tar.gz')
    for image in manifest['images']:
        actual = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']], text=True).strip()
        if actual != image['id']:
            raise RuntimeError('Imported image mismatch: ' + image['tag'])
    (BUILD / 'release-images.json').write_text(json.dumps([i['tag'] for i in manifest['images']]))


def clean(apply=False):
    candidates = []
    # Exact known disposable outputs only. Never recursively remove directories named .cache.
    for repo, paths in (
        ('platform/secretpad-frontend', ['node_modules', 'tooling/tsup/node_modules', 'tooling/stylelint/node_modules',
         'tooling/eslint/node_modules', 'tooling/jest/node_modules', 'packages/dag/node_modules', 'packages/utils/node_modules',
         'apps/platform/node_modules', 'apps/docs/node_modules', 'packages/dag/dist', 'packages/utils/dist']),
        ('platform/secretpad', ['secretpad-common/target']),
        ('.', ['scripts/__pycache__', 'platform/scripts/__pycache__', 'platform/scripts/environments/__pycache__'])):
        base = SOURCE / repo
        for name in paths:
            path = base / name
            if not path.exists() and not path.is_symlink():
                continue
            tracked = subprocess.check_output(['git', '-C', str(base), 'ls-files', '--', name])
            if tracked:
                raise RuntimeError('Refusing to clean tracked files: ' + str(path))
            candidates.append(path)
    for path in candidates:
        print(('remove ' if apply else 'would remove ') + str(path))
        if apply:
            path.unlink() if path.is_symlink() else shutil.rmtree(path)
    if not apply:
        print('Use clean --apply to remove only these reproducible outputs.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='all', choices=('all', 'check', 'bootstrap', 'install-tools', 'sync', 'build', 'up', 'status', 'run', 'package', 'clean'))
    parser.add_argument('--host', default='127.0.0.1', help='IPv4 address bound by public web gateways (default localhost)')
    parser.add_argument('--lan-cidr', default='127.0.0.0/8', help='Allowed IPv4 source network for web access')
    parser.add_argument('--native', action='store_true', help='Run directly; ARM normally uses an amd64 VM')
    parser.add_argument('--offline', type=Path, help='Verified release directory; skips network bootstrap/build')
    parser.add_argument('--output', help='Package output directory, or tar.gz path with --source-only')
    parser.add_argument('--source-only', action='store_true', help='Export tracked source and all pinned submodules; works on macOS')
    parser.add_argument('--with-images', action='store_true', help='Include all full-stack runtime images for offline use')
    parser.add_argument('--no-tests', action='store_true', help='Skip creating real algorithm demo workloads after all')
    parser.add_argument('--apply', action='store_true', help='Apply the narrowly scoped local cache cleanup')
    args = parser.parse_args(argv)
    if sys.version_info < (3, 9):
        parser.error('Python >=3.9 is required; old CentOS releases need a maintained VM host')
    host = ipaddress.IPv4Address(args.host)
    network = ipaddress.IPv4Network(args.lan_cidr)
    if host.is_unspecified or host.is_multicast or host not in network:
        parser.error('--host must be a concrete IPv4 address within --lan-cidr')
    if args.command == 'clean':
        clean(args.apply)
        return
    if args.command == 'package' and args.source_only:
        package(args)
        return
    if args.command == 'sync':
        if args.offline:
            parser.error('sync needs Git/network; offline source uses its recorded manifest')
        if (SOURCE / '.git').exists():
            run('bash', SOURCE / 'scripts/sync-source.sh', env=environment())
        else:
            list(source_files())
            print('Exported source verified; use a Git checkout for remote updates.')
        return
    if platform.system() != 'Linux':
        parser.error('Deployment requires Linux+systemd. Source packaging and local cleanup also work on macOS.')
    if platform.machine() in ('aarch64', 'arm64') and not args.native:
        helper = [sys.executable, SOURCE / 'scripts/amd64-vm.py', '--bind-address', args.host, '--lan-cidr', args.lan_cidr]
        if args.command in ('all', 'up', 'build', 'bootstrap', 'install-tools'):
            with tempfile.TemporaryDirectory() as tmp:
                tar = Path(tmp) / 'source.tar.gz'
                source_package(tar)
                command = helper + ['--bootstrap', '--source-package', tar, 'deploy', args.command]
                if args.no_tests:
                    command.append('--no-tests')
                if args.offline:
                    command += ['--offline', args.offline]
                run(*command)
        else:
            command = helper + [{'check': 'check'}.get(args.command, args.command)]
            if args.output:
                command += ['--output', args.output]
            if args.with_images:
                command += ['--with-images']
            run(*command)
        return
    if platform.machine() not in ('x86_64', 'amd64'):
        parser.error('Full native stack requires amd64; arm64 uses the default amd64 VM fallback')
    if args.command == 'install-tools':
        install_tools()
        return
    if args.command == 'package':
        package(args)
        return
    if args.command not in ('check', 'status', 'sync') and os.geteuid() != 0:
        parser.error('Run deployment/build/run/bootstrap with sudo; package/source export needs read access only')
    if args.command in ('all', 'bootstrap') and not args.offline:
        run('bash', SOURCE / 'scripts/install-deps.sh')
    if args.command == 'bootstrap':
        return
    env = environment()
    backend = [sys.executable, SOURCE / 'scripts/full-deploy.py']
    options = ['--host', args.host, '--lan-cidr', args.lan_cidr]
    def stage(name):
        run(*backend, name, *options, env=env)
    if args.command == 'check':
        stage('preflight')
    elif args.command == 'status':
        stage('status')
    elif args.command == 'run':
        stage('run')
    else:
        if args.offline:
            restore(args.offline)
            env = environment()
        stage('preflight')
        if args.offline:
            pass
        elif args.command in ('all', 'build'):
            if (SOURCE / '.git').exists():
                run('git', '-C', SOURCE, 'submodule', 'update', '--init', '--recursive', env=env)
            else:
                list(source_files())
            stage('build')
        if args.command in ('all', 'up'):
            stage('deploy')
            stage('status')
            if not args.no_tests:
                stage('run')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print('PPCI: ' + str(error), file=sys.stderr)
        sys.exit(1)
