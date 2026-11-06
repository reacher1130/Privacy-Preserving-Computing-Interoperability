#!/usr/bin/env python3
"""Build the current BFIA source in the home Linux machine's isolated build tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

SOURCE = Path(os.environ.get('PPCI_SOURCE_ROOT', '/opt/ppci-source'))
BUILD = Path(os.environ.get('PPCI_BUILD_ROOT', '/opt/ppci-build'))
BASE = 'secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/morse-ecdh-header:20251113'
IMAGE = os.environ.get('BFIA_CPP_IMAGE', 'ppci/bfia-cpp:numerics-20260914-v2')
CACHE = 'ppci-bfia-bazel-cache'
SPU_PIN = '74c6d54e5bff9e5d35ab5a73dda98cd9ccf0bfc8'
BAZEL_SHA = 'a40ac69263440761199fcb8da47ad4e3f328cbe79ffbf4ecc14e5ba252857307'
ALIASES = ['ecdh', 'ecdh-psi', 'ss-compare', 'ss-lr', 'ss-pearson', 'ss-vif', 'ss-xgb']


def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def build():
    bazel = BUILD / 'tools/bazel-6.5.0'
    if not bazel.is_file() or hashlib.sha256(bazel.read_bytes()).hexdigest() != BAZEL_SHA:
        raise RuntimeError('Install the official Bazel 6.5.0 Linux x86_64 binary in ' + str(bazel))
    bazel.chmod(0o755)
    work = BUILD / 'bfia'
    work.mkdir(exist_ok=True)
    for repo in ('secretflow', 'yacl'):
        run('rsync', '-a', '--exclude=.git', '--exclude=__pycache__', '--exclude=bazel-*',
            '--exclude=results', '--exclude=/interconnection-impl/.cache/bazel-home',
            '--exclude=/interconnection-impl/.cache/deps',
            str(SOURCE / 'NewProject' / repo) + '/', str(work / repo) + '/')
    spu = pinned_spu(work)
    # codeload URLs end in a commit; Bazel needs the archive type explicitly.
    bzl = work / 'yacl/bazel/repositories.bzl'
    content = bzl.read_text()
    def archive_type(match):
        block = match.group(0)
        if 'codeload.github.com' in block and not re.search(r'\btype\s*=', block):
            return block.replace('http_archive(', 'http_archive(\n        type = "tar.gz",', 1)
        return block
    bzl.write_text(re.sub(r'http_archive\([\s\S]*?\n    \)', archive_type, content))
    args = ['docker', 'run', '--rm', '--name', 'ppci-bfia-builder', '--network', 'host',
            '--cpus', '3.25', '--memory', '5g', '--ulimit', 'nofile=65536:65536',
            '-v', f'{work}:/build', '-v', f'{BUILD}/tools:/tools:ro',
            '-v', f'{CACHE}:/root/.cache/bazel', '-w', '/build/secretflow/interconnection-impl']
    for key in ('HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY'):
        if os.environ.get(key): args += ['-e', key]
    command = 'python3 -m pip install --index-url https://pypi.org/simple --cache-dir /build/pip "numpy<2" && '
    command += '/tools/bazel-6.5.0 --host_jvm_args=-Xmx1500m build -c opt --jobs=3 --local_cpu_resources=3 --local_ram_resources=4000 --spawn_strategy=standalone '
    command += '--override_repository=spulib=/build/spu --override_repository=yacl=/build/yacl '
    for dep in ('com_envoyproxy_protoc_gen_validate', 'com_google_googletest', 'com_github_intel_ipp'):
        command += f'--override_repository={dep}=/build/secretflow/interconnection-impl/.cache/overridden/{dep} '
    command += 'ic_impl/ic_main'
    run(*args, '--entrypoint', 'bash', BASE, '-c', command)


def pinned_spu(work):
    archive = SOURCE / 'NewProject/thirdparty/spu-build-source.tar.gz'
    manifest = json.loads(archive.with_suffix('').with_suffix('.json').read_text())
    if manifest['commit'] != SPU_PIN or hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['sha256']:
        raise RuntimeError('Pinned BFIA SPU source checksum or commit mismatch')
    spu = work / 'spu'
    marker = spu / '.ppci-source-sha256'
    if spu.is_symlink():
        raise RuntimeError('SPU build source must not be a symbolic link')
    if not marker.exists() or marker.read_text().strip() != manifest['sha256']:
        sys.path.insert(0, str(SOURCE / 'scripts'))
        from portable import unpack
        if spu.exists():
            shutil.rmtree(spu)
        unpack(archive, spu, allow_links=True)
        marker.write_text(manifest['sha256'] + '\n')
    return spu


def image():
    context = BUILD / 'bfia-runtime-image'
    context.mkdir(exist_ok=True)
    # Select the output by its workspace path, without embedding Bazel's host-specific hash.
    run('docker', 'run', '--rm', '-v', f'{CACHE}:/cache:ro', '-v', f'{context}:/out',
        '--entrypoint', 'bash', BASE, '-c',
        'set -eu; files=(/cache/_bazel_root/*/execroot/interconnection-impl/bazel-out/k8-opt/bin/ic_impl/ic_main); '
        'test "${#files[@]}" -eq 1; test -x "${files[0]}"; cp "${files[0]}" /out/ic_main; strip --strip-unneeded /out/ic_main')
    shutil.copyfile(SOURCE / 'NewProject/secretflow/interconnection-impl/docker/docker-conf/entrypoint-slim.sh',
                    context / 'entrypoint.sh')
    (context / 'Dockerfile').write_text('''FROM ppci/bfia-runtime-base:bookworm-20260912
WORKDIR /app
COPY ic_main /app/ic_main
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod 0555 /app/ic_main /app/entrypoint.sh
STOPSIGNAL SIGTERM
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
''')
    run('docker', 'build', '-t', IMAGE, context, env=dict(os.environ, DOCKER_BUILDKIT='0'))
    for alias in ALIASES:
        run('docker', 'tag', IMAGE, f'secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/{alias}:latest')


def python_image():
    context = BUILD / 'bfia-python-image'
    context.mkdir(exist_ok=True)
    recipe = (SOURCE / 'NewProject/scripts/linux-migration/Dockerfile.bfia-python').read_text()
    recipe = recipe.replace('RUN pip install --no-cache-dir',
                            'ARG HTTPS_PROXY\nARG HTTP_PROXY\nCOPY ca-bundle.crt /tmp/ppci-ca-bundle.crt\n'
                            'RUN PIP_CERT=/tmp/ppci-ca-bundle.crt pip install --index-url https://pypi.org/simple --no-cache-dir')
    (context / 'Dockerfile').write_text(recipe)
    ca = os.environ.get('PPCI_CA_BUNDLE') or next(str(p) for p in
        (Path('/etc/ssl/certs/ca-certificates.crt'), Path('/etc/pki/tls/certs/ca-bundle.crt')) if p.is_file())
    shutil.copyfile(ca, context / 'ca-bundle.crt')
    command = ['docker', 'build', '--network=host']
    for key in ('HTTPS_PROXY', 'HTTP_PROXY'):
        if os.environ.get(key): command += ['--build-arg', key]
    run(*command, '-t', 'ppci/bfia-python:amd64-20260908', context,
        env=dict(os.environ, DOCKER_BUILDKIT='0'))


def base_image():
    context = BUILD / 'bfia-base-image'
    context.mkdir(exist_ok=True)
    (context / 'Dockerfile').write_text('''FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 && rm -rf /var/lib/apt/lists/*
''')
    run('docker', 'build', '--platform=linux/amd64', '-t', 'ppci/bfia-runtime-base:bookworm-20260912',
        context, env=dict(os.environ, DOCKER_BUILDKIT='0'))


def import_image():
    archive = Path(os.environ.get('PPCI_ROOT', '/opt/ppci')) / 'images/bfia-cpp-amd64.tar'
    archive.parent.mkdir(exist_ok=True)
    tags = [f'secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/{name}:latest' for name in ALIASES]
    run('docker', 'save', '-o', archive, IMAGE, *tags)
    for node in ('alice', 'bob'):
        run('docker', 'exec', 'gaofeng-kuscia-autonomy-' + node,
            'kuscia', 'image', 'load', '-i', '/home/kuscia/var/images/' + archive.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('build', 'image', 'python', 'base', 'import'))
    args = parser.parse_args()
    {'build': build, 'image': image, 'python': python_image, 'base': base_image, 'import': import_image}[args.stage]()
