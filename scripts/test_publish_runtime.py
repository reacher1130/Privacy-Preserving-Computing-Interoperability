import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publish_runtime', Path(__file__).with_name('publish-runtime.py'))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
IDENTITY = {'release_tag': 'runtime-20261109-abcdef0', 'source_revision': 'a' * 40,
            'input_sha256': 'b' * 64}
IMAGE_ID = 'sha256:' + 'c' * 64
IMAGE_DIGEST = 'sha256:' + 'd' * 64


def release(draft=True):
    return {'id': 123, 'draft': draft, 'prerelease': False,
            'tag_name': IDENTITY['release_tag'], 'target_commitish': IDENTITY['source_revision'],
            'body': publisher.DESCRIPTION + '\n\n' + publisher.seal(IDENTITY),
            'html_url': 'https://github.com/' + publisher.REPOSITORY + '/releases/tag/' + IDENTITY['release_tag']}


def item():
    return {'target': 'ghcr.io/reacher1130/bfia-suite:' + IDENTITY['release_tag'] + '-suite',
            'local_tag': 'ghcr.io/reacher1130/bfia-suite:reviewed', 'id': IMAGE_ID,
            'aliases': ['ghcr.io/reacher1130/bfia-suite:reviewed'],
            'clean_source_build': True, 'component': 'bfia-suite'}


def asset(path):
    return {'id': 456, 'name': path.name, 'state': 'uploaded', 'size': path.stat().st_size,
            'digest': 'sha256:' + publisher.digest(path)}


class PublisherTests(unittest.TestCase):
    def test_unreviewed_release_identity_stops_before_staging_or_authentication(self):
        for tag, checksum in (('../another-directory', 'a' * 64),
                              ('runtime-20261109-abcdef0', 'unreviewed')):
            with self.subTest(tag=tag), patch.dict(os.environ, {'RELEASE_TAG': tag, 'INPUT_SHA256': checksum}, clear=True), \
                 patch.object(publisher, 'digest') as digest, self.assertRaises(ValueError):
                publisher.main()
            digest.assert_not_called()

    def test_release_upload_streams_file_instead_of_buffering_it(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'artifact.tar.gz'
            artifact.write_bytes(b'abcdef')

            def upload(request, timeout):
                self.assertEqual(request.get_header('Content-length'), '6')
                self.assertTrue(hasattr(request.data, 'read'))
                self.assertEqual(request.data.read(3), b'abc')
                self.assertEqual(request.data.read(3), b'def')
                return io.BytesIO(b'{"id":1}')

            with patch.object(publisher.urllib.request, 'urlopen', side_effect=upload):
                self.assertEqual(publisher.api('https://uploads.github.com/repos/owner/repo/releases/1/assets?name=x',
                                               'test-token', upload=artifact), {'id': 1})

    def test_http_reads_retry_but_post_is_reconciled_by_the_caller(self):
        unavailable = urllib.error.HTTPError('https://api.github.com/test', 503, 'temporarily unavailable', {}, None)
        with patch.object(publisher.urllib.request, 'urlopen', side_effect=[unavailable, io.BytesIO(b'{"ok":true}')]) as opened, \
             patch.object(publisher.time, 'sleep'):
            self.assertEqual(publisher.api('test', 'token'), {'ok': True})
            self.assertEqual(opened.call_count, 2)
        with patch.object(publisher.urllib.request, 'urlopen', side_effect=unavailable) as opened:
            with self.assertRaises(urllib.error.HTTPError):
                publisher.api('test', 'token', {'create': 'once'})
            self.assertEqual(opened.call_count, 1)
        unavailable.close()

    def test_draft_recovery_requires_the_same_reviewed_sha_and_source(self):
        previous = release()
        with patch.object(publisher, 'find_release', return_value=previous), patch.object(publisher, 'api') as api:
            self.assertEqual(publisher.draft_release(IDENTITY, 'token'), previous)
            api.assert_not_called()
        for field in ('input_sha256', 'source_revision'):
            changed = dict(IDENTITY, **{field: 'e' * len(IDENTITY[field])})
            with self.subTest(field=field), patch.object(publisher, 'find_release', return_value=previous), \
                 patch.object(publisher, 'api') as api, self.assertRaises(ValueError):
                publisher.draft_release(changed, 'token')
            api.assert_not_called()

    def test_lost_draft_create_response_does_not_create_a_second_release(self):
        unavailable = urllib.error.URLError('response was lost')
        with patch.object(publisher, 'find_release', side_effect=[None, release()]), \
             patch.object(publisher, 'api', side_effect=unavailable) as api:
            self.assertTrue(publisher.draft_release(IDENTITY, 'token')['draft'])
            self.assertEqual(api.call_count, 1)
            self.assertIs(api.call_args.args[2]['draft'], True)

    def test_asset_retry_accepts_server_commit_after_a_lost_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'artifacts.tar.gz'; path.write_bytes(b'reviewed data')
            remote = asset(path)
            calls = []
            def api(name, token, **kwargs):
                calls.append((name, kwargs))
                if kwargs.get('upload'):
                    raise urllib.error.URLError('upload response lost after commit')
                return release()
            with patch.object(publisher, 'api', side_effect=api), \
                 patch.object(publisher, 'release_assets', side_effect=[{}, {path.name: remote}, {path.name: remote}]), \
                 patch.object(publisher.time, 'sleep'):
                publisher.ensure_assets(release(), IDENTITY, {path.name: path}, 'token', {path.name: publisher.digest(path)})
            self.assertEqual(sum('upload' in kwargs for _, kwargs in calls), 1)
            self.assertFalse(any(kwargs.get('method') == 'DELETE' for _, kwargs in calls))

    def test_partial_draft_asset_cleanup_is_scoped_to_its_owned_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'artifacts.tar.gz'; path.write_bytes(b'reviewed data')
            partial = {'id': 789, 'name': path.name, 'state': 'starter', 'size': 0}
            calls = []
            def api(name, token, **kwargs):
                calls.append((name, kwargs))
                return asset(path) if kwargs.get('upload') else release()
            with patch.object(publisher, 'api', side_effect=api), \
                 patch.object(publisher, 'release_assets', side_effect=[{path.name: partial}, {path.name: asset(path)}]):
                publisher.ensure_assets(release(), IDENTITY, {path.name: path}, 'token', {path.name: publisher.digest(path)})
            self.assertEqual([name for name, kwargs in calls if kwargs.get('method') == 'DELETE'],
                             [publisher.API_RELEASES + '/assets/789'])
            unrelated = release(); unrelated['body'] = 'another release'
            with patch.object(publisher, 'api', return_value=unrelated) as api, \
                 patch.object(publisher, 'release_assets') as assets, self.assertRaises(ValueError):
                publisher.ensure_assets(unrelated, IDENTITY, {path.name: path}, 'token', {path.name: publisher.digest(path)})
            assets.assert_not_called()
            self.assertFalse(any(call.kwargs.get('method') == 'DELETE' for call in api.call_args_list))

    def test_matching_published_release_is_read_only_and_mismatch_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'artifacts.tar.gz'; path.write_bytes(b'reviewed data')
            remote = asset(path)
            with patch.object(publisher, 'api', return_value=release(False)) as api, \
                 patch.object(publisher, 'release_assets', return_value={path.name: remote}):
                publisher.ensure_assets(release(False), IDENTITY, {path.name: path}, 'token', {path.name: publisher.digest(path)})
            self.assertTrue(all(not call.kwargs for call in api.call_args_list))
            remote['digest'] = 'sha256:' + 'e' * 64
            with patch.object(publisher, 'api', return_value=release(False)) as api, \
                 patch.object(publisher, 'release_assets', return_value={path.name: remote}), \
                 self.assertRaisesRegex(ValueError, 'Immutable'):
                publisher.ensure_assets(release(False), IDENTITY, {path.name: path}, 'token', {path.name: publisher.digest(path)})
            self.assertTrue(all(not call.kwargs for call in api.call_args_list))

    def test_reviewed_asset_cannot_change_during_release_metadata_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'artifacts.tar.gz'; path.write_bytes(b'reviewed data')
            checksum = publisher.digest(path)
            def api(name, token, **kwargs):
                path.write_bytes(b'changed data')
                self.assertFalse(kwargs)
                return release()
            with patch.object(publisher, 'api', side_effect=api), \
                 patch.object(publisher, 'release_assets', return_value={}), \
                 self.assertRaisesRegex(ValueError, 'changed during'):
                publisher.ensure_assets(release(), IDENTITY, {path.name: path}, 'token', {path.name: checksum})

    def test_image_aliases_deduplicate_and_conflicting_content_stops_up_front(self):
        first = item()
        self.assertEqual(len(publisher.reviewed_images([first, first], IDENTITY['release_tag'])), 1)
        self.assertEqual(publisher.reviewed_images([first], IDENTITY['release_tag'])[0]['aliases'], first['aliases'])
        for changed in (dict(first, id='sha256:' + 'e' * 64),
                        dict(first, id='sha256:' + 'e' * 64, target=first['target'] + '-other')):
            with self.subTest(target=changed['target']), self.assertRaises(ValueError):
                publisher.reviewed_images([first, changed], IDENTITY['release_tag'])

    def test_image_export_pins_config_id_and_checkpoint_skips_export_on_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory); image = item(); calls = []
            def command(*args, **kwargs):
                calls.append((args, kwargs))
                if args[:3] == ('docker', 'image', 'inspect'):
                    return '[{"Size":1024}]'
                if args[:3] == ('docker', 'image', 'save'):
                    Path(args[4]).write_bytes(b'fake Docker archive')
                    self.assertEqual(args[5], IMAGE_ID)
                if len(args) > 1 and args[1] == 'digest':
                    return IMAGE_DIGEST
                if len(args) > 1 and args[1] == 'manifest':
                    return json.dumps({'config': {'digest': IMAGE_ID}})
                if len(args) > 1 and args[1] == 'config':
                    return '{"architecture":"amd64","os":"linux"}'
                return ''
            with patch.object(publisher, 'command', side_effect=command), \
                 patch.object(publisher.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 10 ** 12})()):
                rows = publisher.publish_images([image], staging, IDENTITY, 'token', immutable=False)
                self.assertEqual(rows[0]['id'], IMAGE_ID)
                publisher.publish_images([image], staging, IDENTITY, 'token', immutable=False)
            self.assertEqual(sum(args[:3] == ('docker', 'image', 'save') for args, _ in calls), 1)
            self.assertEqual(next(kwargs['timeout'] for args, kwargs in calls if args[:3] == ('docker', 'image', 'save')), 300)
            self.assertEqual(next(kwargs['timeout'] for args, kwargs in calls if len(args) > 1 and args[1] == 'push'), 1800)
            for args, kwargs in calls:
                if 'env' in kwargs:
                    self.assertNotIn('GH_TOKEN', kwargs['env'])

    def test_published_image_config_must_match_the_reviewed_id(self):
        responses = [IMAGE_DIGEST, json.dumps({'config': {'digest': 'sha256:' + 'e' * 64}}),
                     '{"architecture":"amd64","os":"linux"}']
        with patch.object(publisher, 'command', side_effect=responses), self.assertRaisesRegex(ValueError, 'content ID'):
            publisher.remote_image(item(), {})

    def test_docker_and_registry_commands_have_a_default_metadata_timeout(self):
        result = subprocess.CompletedProcess([], 0, stdout=b'ok', stderr=b'')
        with patch.object(publisher.subprocess, 'run', return_value=result) as run:
            self.assertEqual(publisher.command('crane', 'digest', 'image'), 'ok')
            self.assertEqual(run.call_args.kwargs['timeout'], 60)


if __name__ == '__main__':
    unittest.main()
