#!/usr/bin/env python3
"""Publish reviewed clean images and finish an owned, resumable draft release."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'reacher1130/Privacy-Preserving-Computing-Interoperability'
REGISTRIES = {'ghcr.io/reacher1130/ppci-runtime', 'ghcr.io/reacher1130/bfia-suite'}
CRANE = '/opt/ppci-tools/crane'
API_RELEASES = 'repos/' + REPOSITORY + '/releases'
MAX_ASSET_BYTES = 2 * 1024 ** 3
DESCRIPTION = 'Prebuilt Linux amd64 runtime. Program artifacts and clean images only; no deployment identities or business data.'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.publish-', mode='w', delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(value, output, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def command(*args, data=None, env=None, timeout=60):
    return subprocess.run(list(map(str, args)), input=data, env=env, check=True, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()


def transient(error):
    if isinstance(error, urllib.error.HTTPError):
        return error.code in (408, 429, 500, 502, 503, 504)
    return isinstance(error, (urllib.error.URLError, TimeoutError, http.client.HTTPException, json.JSONDecodeError))


def api(path, token, data=None, upload=None, method=None):
    if path.startswith('https://uploads.github.com/'):
        url = path
    elif '://' not in path:
        url = 'https://api.github.com/' + path
    else:
        raise ValueError('Unexpected release API host')
    method = method or ('POST' if data is not None or upload is not None else 'GET')
    headers = {'Authorization': 'Bearer ' + token, 'User-Agent': 'ppci-runtime-release',
               'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    body = None if data is None else json.dumps(data).encode()
    if body is not None:
        headers['Content-Type'] = 'application/json'
    # POST reconciliation belongs to the release/asset caller: a lost response may already have committed it.
    for attempt in range(3):
        try:
            if upload is not None:
                with upload.open('rb') as stream:
                    headers.update({'Content-Type': 'application/octet-stream',
                                    'Content-Length': str(os.fstat(stream.fileno()).st_size)})
                    request = urllib.request.Request(url, data=stream, headers=headers, method=method)
                    with urllib.request.urlopen(request, timeout=900) as response:
                        raw = response.read()
            else:
                request = urllib.request.Request(url, data=body, headers=headers, method=method)
                with urllib.request.urlopen(request, timeout=60) as response:
                    raw = response.read()
            return json.loads(raw) if raw else None
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException, json.JSONDecodeError) as error:
            if method not in ('GET', 'PATCH', 'DELETE') or not transient(error) or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def seal(identity):
    return '<!-- ppci-reviewed-input:' + json.dumps(identity, sort_keys=True, separators=(',', ':')) + ' -->'


def verify_release(release, identity):
    if (release.get('tag_name') != identity['release_tag']
            or release.get('target_commitish') != identity['source_revision']
            or release.get('body') != DESCRIPTION + '\n\n' + seal(identity)
            or release.get('prerelease') is not False
            or not isinstance(release.get('id'), int)):
        raise ValueError('The existing release is not sealed to this reviewed input and source')
    return release


def find_release(tag, token):
    found = []
    for page in range(1, 11):
        releases = api(API_RELEASES + '?per_page=100&page=' + str(page), token)
        found.extend(item for item in releases if item.get('tag_name') == tag)
        if len(releases) < 100:
            break
    else:
        raise ValueError('Release inventory exceeds its review limit')
    if len(found) > 1:
        raise ValueError('More than one release uses the reviewed tag')
    return found[0] if found else None


def draft_release(identity, token):
    previous = find_release(identity['release_tag'], token)
    if previous:
        return verify_release(previous, identity)
    body = {'tag_name': identity['release_tag'], 'target_commitish': identity['source_revision'],
            'name': identity['release_tag'], 'body': DESCRIPTION + '\n\n' + seal(identity),
            'draft': True, 'prerelease': False}
    for attempt in range(3):
        try:
            return verify_release(api(API_RELEASES, token, body), identity)
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException, json.JSONDecodeError) as error:
            if not transient(error) and not (isinstance(error, urllib.error.HTTPError) and error.code == 422):
                raise
            previous = find_release(identity['release_tag'], token)
            if previous:
                return verify_release(previous, identity)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def release_assets(release, token):
    assets = api(API_RELEASES + '/' + str(release['id']) + '/assets?per_page=100', token)
    if len(assets) >= 100 or len({item['name'] for item in assets}) != len(assets):
        raise ValueError('Unexpected or duplicate release asset inventory')
    return {item['name']: item for item in assets}


def asset_matches(asset, path, checksum):
    return (asset.get('state') == 'uploaded' and asset.get('size') == path.stat().st_size
            and asset.get('digest') == 'sha256:' + checksum)


def ensure_assets(release, identity, paths, token, checksums):
    allowed = set(paths)
    if allowed != set(checksums):
        raise ValueError('Release asset checksum inventory does not match')
    upload_base = 'https://uploads.github.com/' + API_RELEASES + '/' + str(release['id']) + '/assets'
    for name, path in paths.items():
        checksum = checksums[name]
        for attempt in range(3):
            if path.is_symlink() or digest(path) != checksum:
                raise ValueError('A sealed release asset changed before upload: ' + name)
            current = verify_release(api(API_RELEASES + '/' + str(release['id']), token), identity)
            assets = release_assets(current, token)
            if set(assets) - allowed:
                raise ValueError('The reviewed release contains unexpected assets')
            asset = assets.get(name)
            if asset is not None and asset_matches(asset, path, checksum):
                break
            if current['draft'] is not True:
                raise ValueError('Immutable published release assets do not match the reviewed files')
            if digest(path) != checksum:
                raise ValueError('A sealed release asset changed during publication: ' + name)
            if asset is not None:
                if asset.get('state') == 'uploaded' and asset.get('size', 0) > 0:
                    raise ValueError('An uploaded draft asset has another digest; retain it for review')
                try:
                    api(API_RELEASES + '/assets/' + str(asset['id']), token, method='DELETE')
                except urllib.error.HTTPError as error:
                    if error.code != 404:
                        raise
            try:
                uploaded = api(upload_base + '?name=' + urllib.parse.quote(name), token, upload=path)
                if asset_matches(uploaded, path, checksum):
                    print('Verified upload ' + name, flush=True)
                    break
            except (urllib.error.URLError, TimeoutError, http.client.HTTPException, json.JSONDecodeError) as error:
                if not transient(error) and not (isinstance(error, urllib.error.HTTPError) and error.code == 422):
                    raise
            if attempt == 2:
                raise ValueError('Release asset upload did not complete with the expected digest: ' + name)
            time.sleep(2 ** attempt)
        else:
            raise ValueError('Release asset retry limit exceeded')
    assets = release_assets(release, token)
    if set(assets) != allowed or any(digest(path) != checksums[name]
                                   or not asset_matches(assets[name], path, checksums[name])
                                   for name, path in paths.items()):
        raise ValueError('Release assets did not pass final SHA256 verification')


def reviewed_images(images, tag):
    if not isinstance(images, list) or not images or len(images) > 32:
        raise ValueError('Unexpected clean image inventory')
    targets, aliases = {}, {}
    for item in images:
        target = item['target']
        registry, version = target.rsplit(':', 1)
        if registry not in REGISTRIES or len(version) > 128 or not re.fullmatch(re.escape(tag) + r'-[a-z0-9._-]+', version):
            raise ValueError('Unexpected owned image target')
        if (not isinstance(item['local_tag'], str) or item['local_tag'].startswith('ppci-migration/')
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./:_-]*', item['local_tag'])
                or item.get('clean_source_build') is not True or not re.fullmatch('sha256:[0-9a-f]{64}', item['id'])):
            raise ValueError('Never publish unreviewed images or historical runtime snapshots')
        if not isinstance(item['aliases'], list) or not item['aliases'] or len(item['aliases']) > 64:
            raise ValueError('Unexpected image aliases')
        for alias in item['aliases']:
            if not isinstance(alias, str) or not re.fullmatch(r'[a-z0-9][a-z0-9./:_-]*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', alias):
                raise ValueError('Invalid local runtime alias')
            if alias in aliases and aliases[alias] != item['id']:
                raise ValueError('Runtime alias names conflicting reviewed images')
            aliases[alias] = item['id']
        previous = targets.get(target)
        if previous:
            if previous['id'] != item['id'] or previous.get('component') != item.get('component'):
                raise ValueError('Publication target names conflicting reviewed images')
            previous['aliases'] = list(dict.fromkeys(previous['aliases'] + item['aliases']))
        else:
            targets[target] = dict(item, aliases=list(dict.fromkeys(item['aliases'])))
    return list(targets.values())


def remote_image(item, settings):
    for attempt in range(3):
        try:
            image_digest = command(CRANE, 'digest', item['target'], env=settings)
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_digest):
                raise ValueError('Invalid published image digest')
            registry = item['target'].rsplit(':', 1)[0]
            reference = registry + '@' + image_digest
            manifest = json.loads(command(CRANE, 'manifest', reference, env=settings))
            config = json.loads(command(CRANE, 'config', reference, env=settings))
            if manifest.get('config', {}).get('digest') != item['id'] or config.get('architecture') != 'amd64' or config.get('os') != 'linux':
                raise ValueError('Published image does not match the reviewed content ID and platform')
            return reference
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            if attempt == 2:
                detail = (error.stderr or str(error).encode()).decode(errors='replace')
                detail = re.sub(r'(?i)(authorization:\s*(?:bearer|basic)\s+)\S+', r'\1[redacted]', detail)
                detail = re.sub(r'(https?://[^\s?]+)\?\S+', r'\1?[redacted]', detail)
                raise RuntimeError('Registry metadata read failed after 3 attempts: ' + detail[-2000:]) from None
            time.sleep(2 ** (attempt + 1))


def publish_images(images, staging, identity, token, immutable):
    checkpoint_path = staging / 'registry-published.json'
    checkpoint = dict(identity, targets={})
    if checkpoint_path.exists():
        if checkpoint_path.is_symlink():
            raise ValueError('Publication checkpoint is a symbolic link')
        checkpoint = json.loads(checkpoint_path.read_text())
        if any(checkpoint.get(key) != value for key, value in identity.items()) or set(checkpoint['targets']) - {item['target'] for item in images}:
            raise ValueError('Publication checkpoint belongs to another reviewed input')
    rows, aliases = [], set()
    with tempfile.TemporaryDirectory(prefix='ppci-publish-', dir=staging) as directory:
        settings = {key: value for key, value in os.environ.items() if key not in ('GH_TOKEN', 'GITHUB_TOKEN')}
        settings['DOCKER_CONFIG'] = directory
        command(CRANE, 'auth', 'login', 'ghcr.io', '-u', 'reacher1130', '--password-stdin', data=token.encode(), env=settings)
        archive = Path(directory) / 'image.tar'
        for item in images:
            saved = checkpoint['targets'].get(item['target'])
            if not immutable and not saved:
                size = json.loads(command('docker', 'image', 'inspect', item['id']))[0]['Size']
                if shutil.disk_usage(staging).free < size + 1024 ** 3:
                    raise ValueError('Insufficient staging disk for the next immutable image export')
                command('docker', 'image', 'save', '-o', archive, item['id'], timeout=300)
                command(CRANE, 'push', archive, item['target'], env=settings, timeout=1800)
                archive.unlink()
            reference = remote_image(item, settings)
            if saved and saved != {'reference': reference, 'id': item['id']}:
                raise ValueError('A previously published release image changed')
            checkpoint['targets'][item['target']] = {'reference': reference, 'id': item['id']}
            write_json(checkpoint_path, checkpoint)
            for alias in item['aliases']:
                if alias in aliases:
                    continue
                aliases.add(alias)
                row = {'reference': reference, 'tag': alias, 'id': item['id']}
                if item.get('component'):
                    row['component'] = item['component']
                rows.append(row)
            print('Verified image ' + item['target'] + ' ' + reference.rsplit('@', 1)[1], flush=True)
    return rows


def main():
    os.umask(0o077)
    tag, expected = os.environ['RELEASE_TAG'], os.environ['INPUT_SHA256']
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
    identity = {'release_tag': tag, 'source_revision': revision, 'input_sha256': expected}
    files = prepared['files']
    if not isinstance(files, dict) or set(files) - {'artifacts.tar.gz', 'tools.tar.gz'} or 'artifacts.tar.gz' not in files:
        raise ValueError('Unexpected release files')
    for name, checksum in files.items():
        path = staging / name
        if not re.fullmatch('[0-9a-f]{64}', checksum) or path.is_symlink() or digest(path) != checksum:
            raise ValueError('Prepared artifact changed: ' + name)
        if not 0 < path.stat().st_size < MAX_ASSET_BYTES:
            raise ValueError('Prepared artifact exceeds the release upload size limit: ' + name)
    images = reviewed_images(prepared['images'], tag)
    for item in images:
        actual = json.loads(command('docker', 'image', 'inspect', item['id']))[0]
        if actual['Id'] != item['id'] or actual['Architecture'] != 'amd64' or actual['Os'] != 'linux':
            raise ValueError('Prepared image changed: ' + item['local_tag'])
    token = os.environ['GH_TOKEN']
    release = draft_release(identity, token)
    published = publish_images(images, staging, identity, token, immutable=release['draft'] is not True)
    # Recheck artifacts after potentially long image uploads, before exposing any release asset.
    if any(digest(staging / name) != checksum for name, checksum in files.items()):
        raise ValueError('Prepared artifacts changed during image publication')
    manifest = {'format': 2, 'platform': 'linux/amd64', 'runtime_data_included': False,
                'source_revision': revision, 'release_tag': tag, 'sha256': files, 'images': published}
    manifest_path = staging / 'manifest.json'
    write_json(manifest_path, manifest)
    hashes = staging / 'SHA256SUMS'
    hashes.write_text(''.join(digest(staging / name) + '  ' + name + '\n' for name in [*sorted(files), 'manifest.json']))
    paths = {name: staging / name for name in [*sorted(files), 'manifest.json', 'SHA256SUMS']}
    checksums = {**files, 'manifest.json': digest(manifest_path), 'SHA256SUMS': digest(hashes)}
    ensure_assets(release, identity, paths, token, checksums)
    if release['draft'] is True:
        release = verify_release(api(API_RELEASES + '/' + str(release['id']), token,
                                     {'draft': False}, method='PATCH'), identity)
        if release['draft'] is not False:
            raise ValueError('The verified draft was not published')
    receipt = {'release_url': release['html_url'],
               'manifest_url': release['html_url'].replace('/tag/', '/download/') + '/manifest.json',
               'manifest_sha256': digest(manifest_path), 'images': published}
    write_json(staging / 'published.json', receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != 'images'}))


if __name__ == '__main__':
    main()
