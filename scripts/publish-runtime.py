#!/usr/bin/env python3
"""Publish a reviewed server staging directory; never build or snapshot live containers."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'reacher1130/Privacy-Preserving-Computing-Interoperability'
REGISTRIES = {'ghcr.io/reacher1130/ppci-runtime', 'ghcr.io/reacher1130/bfia-suite'}
CRANE = '/opt/ppci-tools/crane'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def command(*args, data=None, env=None):
    return subprocess.run(list(map(str, args)), input=data, env=env, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()


def api(path, token, data=None, upload=None):
    url = path if path.startswith('https://uploads.github.com/') else 'https://api.github.com/' + path
    headers = {'Authorization': 'Bearer ' + token, 'User-Agent': 'ppci-runtime-release',
               'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if upload is not None:
        headers.update({'Content-Type': 'application/octet-stream', 'Content-Length': str(upload.stat().st_size)})
        with upload.open('rb') as stream:
            request = urllib.request.Request(url, data=stream, headers=headers, method='POST')
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.load(response)
    body = None if data is None else json.dumps(data).encode()
    if body is not None:
        headers['Content-Type'] = 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=60) as response:
        return json.load(response)


def main():
    os.umask(0o077)
    tag = os.environ['RELEASE_TAG']
    expected = os.environ['INPUT_SHA256']
    if not re.fullmatch(r'runtime-\d{8}-[0-9a-f]{7,40}', tag) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('Invalid reviewed release identity')
    staging = Path('/opt/ppci-build/ppci-releases') / tag
    source = staging / 'input.json'
    if source.is_symlink() or digest(source) != expected:
        raise ValueError('Prepared release input changed')
    prepared = json.loads(source.read_text())
    revision = os.environ['GITHUB_SHA']
    if prepared['source_revision'] != revision or prepared['release_tag'] != tag:
        raise ValueError('Workflow source does not match reviewed build')
    files = prepared['files']
    if set(files) - {'artifacts.tar.gz', 'tools.tar.gz'} or 'artifacts.tar.gz' not in files:
        raise ValueError('Unexpected release files')
    for name, checksum in files.items():
        path = staging / name
        if path.is_symlink() or digest(path) != checksum:
            raise ValueError('Prepared artifact changed: ' + name)
    images = prepared['images']
    if not images or len(images) > 32:
        raise ValueError('Unexpected clean image inventory')
    for item in images:
        target = item['target']
        registry, version = target.rsplit(':', 1)
        if registry not in REGISTRIES or not re.fullmatch(re.escape(tag) + r'-[a-z0-9._-]+', version):
            raise ValueError('Unexpected owned image target')
        if item['local_tag'].startswith('ppci-migration/') or not item.get('clean_source_build'):
            raise ValueError('Never publish historical runtime snapshots')
        actual = json.loads(command('docker', 'image', 'inspect', item['local_tag']))[0]
        if actual['Id'] != item['id'] or actual['Architecture'] != 'amd64' or actual['Os'] != 'linux':
            raise ValueError('Prepared image changed: ' + item['local_tag'])
    token = os.environ['GH_TOKEN']
    try:
        api('repos/' + REPOSITORY + '/releases/tags/' + tag, token)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        raise ValueError('Immutable release already exists')
    published = []
    with tempfile.TemporaryDirectory(prefix='ppci-publish-', dir=staging) as directory:
        settings = dict(os.environ, DOCKER_CONFIG=directory)
        command(CRANE, 'auth', 'login', 'ghcr.io', '-u', 'reacher1130', '--password-stdin', data=token.encode(), env=settings)
        archive = Path(directory) / 'image.tar'
        for item in images:
            command('docker', 'image', 'save', '-o', archive, item['local_tag'])
            command(CRANE, 'push', archive, item['target'], env=settings)
            image_digest = command(CRANE, 'digest', item['target'], env=settings)
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_digest):
                raise ValueError('Invalid published image digest')
            registry = item['target'].rsplit(':', 1)[0]
            if json.loads(command(CRANE, 'config', registry + '@' + image_digest, env=settings))['architecture'] != 'amd64':
                raise ValueError('Published image architecture mismatch')
            for alias in item['aliases']:
                row = {'reference': registry + '@' + image_digest, 'tag': alias, 'id': item['id']}
                if item.get('component'):
                    row['component'] = item['component']
                published.append(row)
            archive.unlink()
            print('Published ' + item['target'] + ' ' + image_digest, flush=True)
    manifest = {'format': 2, 'platform': 'linux/amd64', 'runtime_data_included': False,
                'source_revision': revision, 'release_tag': tag, 'sha256': files, 'images': published}
    manifest_path = staging / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    hashes = staging / 'SHA256SUMS'
    hashes.write_text(''.join(digest(staging / name) + '  ' + name + '\n'
                             for name in [*files, 'manifest.json']))
    release = api('repos/' + REPOSITORY + '/releases', token,
                  {'tag_name': tag, 'target_commitish': revision, 'name': tag,
                   'body': 'Prebuilt Linux amd64 runtime. Program artifacts and clean images only; no deployment identities or business data.',
                   'draft': False, 'prerelease': False})
    upload_base = release['upload_url'].split('{', 1)[0]
    for name in [*files, 'manifest.json', 'SHA256SUMS']:
        api(upload_base + '?name=' + urllib.parse.quote(name), token, upload=staging / name)
        print('Uploaded ' + name, flush=True)
    receipt = {'release_url': release['html_url'], 'manifest_url': release['html_url'].replace('/tag/', '/download/') + '/manifest.json',
               'manifest_sha256': digest(manifest_path), 'images': published}
    (staging / 'published.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({key: value for key, value in receipt.items() if key != 'images'}))


if __name__ == '__main__':
    main()
