"""Offline trust-boundary and task-lifecycle checks; no containers are started."""
import argparse
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('suite_kuscia', Path(__file__).with_name('bfia-suite-kuscia.py'))
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)
RUN = '11111111-2222-3333-4444-555555555555'
CONFIG = suite.config_values('ghcr.io/reacher1130/bfia-suite@sha256:' + 'a' * 64,
                             'ghcr.io/reacher1130/bfia-suite:20261109-test', 'sha256:' + 'b' * 64)


def frame(payload, name=None):
    kind = 'FILE' if name else 'BUNDLE'
    tokens = [RUN] + ([name] if name else [])
    header = ' '.join(tokens + [hashlib.sha256(payload).hexdigest(), str(len(payload))])
    encoded = base64.b64encode(payload).decode()
    chunks = '\n'.join('PPCI_BFIA_' + kind + '_DATA ' + encoded[i:i + 4096] for i in range(0, len(encoded), 4096))
    return 'PPCI_BFIA_' + kind + '_BEGIN ' + header + '\n' + chunks + '\nPPCI_BFIA_' + kind + '_END ' + ' '.join(tokens) + '\n'


def bundle(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            if isinstance(content, tarfile.TarInfo):
                archive.addfile(content)
            else:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def passing_files():
    entries = {'exit-code': b'0\n'}
    for language, algorithms, suffix in (('python', suite.PYTHON, '.stdout.log'), ('cpp', suite.CPP, '.log')):
        numerical, protocol = {}, {}
        for algorithm in algorithms:
            numerical[algorithm] = {'pass': True}
            hashes = {}
            for party in ('alice', 'bob'):
                content = ('actual event ' + language + ' ' + algorithm + ' ' + party + '\n').encode()
                entries[f'{language}/{RUN}/{algorithm}/{party}{suffix}'] = content
                hashes[party + suffix] = hashlib.sha256(content).hexdigest()
            protocol[algorithm] = {'pass': True, 'log_sha256': hashes}
        entries[f'{language}/{RUN}/numerical-validation.json'] = json.dumps(numerical).encode()
        entries[f'{language}/{RUN}/protocol-validation.json'] = json.dumps(protocol).encode()
    return entries


class SuiteKusciaTests(unittest.TestCase):
    def test_only_fixed_digest_and_release_tag_can_be_installed(self):
        for image, tag, image_id in (
            ('ghcr.io/reacher1130/bfia-suite:latest', CONFIG['image_tag'], CONFIG['image_id']),
            (CONFIG['image_ref'], 'ghcr.io/reacher1130/bfia-suite:latest', CONFIG['image_id']),
            (CONFIG['image_ref'], 'elsewhere/bfia-suite:20261109', CONFIG['image_id']),
            (CONFIG['image_ref'], CONFIG['image_tag'], 'unverified'),
        ):
            with self.subTest(image=image, tag=tag), self.assertRaises(ValueError):
                suite.config_values(image, tag, image_id)

    def test_job_and_appimage_have_one_local_party_and_no_host_privileges(self):
        job = suite.job(CONFIG, RUN)
        self.assertEqual(job['spec']['tasks'][0]['taskID'], RUN)
        self.assertEqual(job['spec']['tasks'][0]['parties'], [{'domainID': 'alice', 'role': 'runner'}])
        app = suite.app_image(CONFIG)
        self.assertEqual(app['spec']['image']['id'], CONFIG['image_id'])
        container = app['spec']['deployTemplates'][0]['spec']['containers'][0]
        self.assertEqual(container['args'], ['--kuscia'])
        self.assertIn('kuscia.secretflow/task-id', container['env'][0]['valueFrom']['fieldRef']['fieldPath'])
        self.assertNotIn('securityContext', container)
        self.assertNotIn('volumeMounts', container)
        with self.assertRaises(ValueError):
            suite.job(CONFIG, RUN + ';touch /tmp/unsafe')

    def test_chunked_frames_check_hash_run_and_live_path(self):
        name = f'cpp/{RUN}/ss-lr/alice.log'
        payload = b'actual log\n' * 1000
        self.assertEqual(list(suite.frames(frame(payload, name), RUN)), [('FILE', name, payload)])
        self.assertEqual(list(suite.frames(frame(payload), RUN)), [('BUNDLE', None, payload)])
        self.assertEqual(list(suite.frames(frame(payload)[:-60], RUN)), [])
        with self.assertRaises(ValueError):
            list(suite.frames(frame(payload).replace(hashlib.sha256(payload).hexdigest(), '0' * 64), RUN))
        with self.assertRaises(ValueError):
            list(suite.frames(frame(payload, 'state.json'), RUN))
        with self.assertRaises(ValueError):
            list(suite.frames(frame(payload).replace(RUN, '0' + RUN[1:]), RUN))

    def test_archive_rejects_traversal_links_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary).resolve()
            link = tarfile.TarInfo(f'cpp/{RUN}/link')
            link.type, link.linkname = tarfile.SYMTYPE, '/etc/passwd'
            for entries in ({'../escape': b'bad', 'exit-code': b'0'}, {link.name: link, 'exit-code': b'0'},
                            {f'python/{RUN}/../../state.json': b'bad', 'exit-code': b'0'}):
                with self.subTest(entries=list(entries)), self.assertRaises(ValueError):
                    suite.unpack_bundle(bundle(entries), dest, RUN)
            self.assertFalse((dest.parent / 'escape').exists())
            duplicate = io.BytesIO()
            with tarfile.open(fileobj=duplicate, mode='w:gz') as archive:
                for _ in range(2):
                    info = tarfile.TarInfo('exit-code'); info.size = 1
                    archive.addfile(info, io.BytesIO(b'0'))
            with self.assertRaises(ValueError):
                suite.unpack_bundle(duplicate.getvalue(), dest, RUN)

    def test_offline_install_verifies_tag_content_id_without_repo_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            def command(*args, **kwargs):
                if args[-1] == CONFIG['image_ref']:
                    return subprocess.CompletedProcess(args, 1, stdout=b'', stderr=b'not found')
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps([
                    {'Id': CONFIG['image_id'], 'Architecture': 'amd64'}]).encode(), stderr=b'')
            args = argparse.Namespace(runtime_root=root, image_ref=CONFIG['image_ref'],
                                      image_tag=CONFIG['image_tag'], image_id=CONFIG['image_id'],
                                      container=CONFIG['container'], domain=CONFIG['domain'])
            with patch.object(suite, 'command', side_effect=command), \
                 patch.object(suite, 'object_json', return_value=None), \
                 patch.object(suite, 'import_image') as imported, \
                 patch.object(suite, 'kubectl'):
                suite.install_locked(args)
            imported.assert_called_once_with(CONFIG)
            self.assertEqual(suite.read_config(root), CONFIG)

    def test_complete_reports_require_all_eight_actual_log_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary).resolve()
            self.assertEqual(suite.unpack_bundle(bundle(passing_files()), dest, RUN), 0)
            self.assertTrue(suite.verified_reports(dest, RUN))
            (dest / 'cpp' / RUN / 'ss-lr/alice.log').write_text('changed log')
            self.assertFalse(suite.verified_reports(dest, RUN))

    def test_output_parent_symlinks_cannot_redirect_a_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            dest, outside = Path(temporary).resolve() / 'run', Path(temporary).resolve() / 'outside'
            dest.mkdir(); outside.mkdir(); (dest / 'cpp').symlink_to(outside)
            with self.assertRaises(RuntimeError):
                suite.private_write(dest / 'cpp' / RUN / 'ss-lr/alice.log', b'bad')
            self.assertFalse((outside / RUN).exists())
            self.assertFalse((outside / RUN / 'ss-lr/alice.log').exists())

    def test_kuscia_completion_publishes_reports_and_exit_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); dest = root / 'runs' / RUN; dest.mkdir(parents=True)
            logs = frame(b'live tail', f'cpp/{RUN}/ss-lr/alice.log') + frame(bundle(passing_files()))
            state = {'metadata': {'uid': 'job-uid'}, 'status': {'phase': 'Running'}}
            done = {'metadata': {'uid': 'job-uid'}, 'status': {'phase': 'Succeeded'}}
            task = {'metadata': {'uid': 'task-uid'}}
            pods = {'items': [{'metadata': {'name': 'suite-pod', 'annotations': {'kuscia.secretflow/image-id': CONFIG['image_id']}}}]}
            def kubectl(config, *args, **kwargs):
                content = json.dumps({'metadata': {'uid': 'job-uid'}}).encode() if args[0] == 'create' else logs.encode()
                return subprocess.CompletedProcess(args, 0, stdout=content, stderr=b'')
            with patch.dict('os.environ', {'PPCI_BFIA_SUITE_ROOT': str(root)}), \
                 patch.object(suite, 'read_config', return_value=CONFIG), \
                 patch.object(suite, 'object_json', side_effect=[{'items': []}, state, task, pods, done, task, pods]), \
                 patch.object(suite, 'kubectl', side_effect=kubectl), patch.object(suite.time, 'sleep'), \
                 patch.object(suite, 'cancel_own_job') as cancel:
                suite.execute(argparse.Namespace(run_id=RUN, runtime_root=root))
            self.assertEqual((dest / 'exit-code').read_text(), '0\n')
            self.assertTrue(suite.verified_reports(dest, RUN))
            cancel.assert_not_called()

    def test_timeout_cancels_only_its_created_job_and_records_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); dest = root / 'runs' / RUN; dest.mkdir(parents=True)
            created = subprocess.CompletedProcess([], 0, stdout=b'{"metadata":{"uid":"only-this-uid"}}', stderr=b'')
            with patch.dict('os.environ', {'PPCI_BFIA_SUITE_ROOT': str(root)}), \
                 patch.object(suite, 'read_config', return_value=CONFIG), \
                 patch.object(suite, 'object_json', return_value={'items': []}), \
                 patch.object(suite, 'kubectl', return_value=created), \
                 patch.object(suite.time, 'monotonic', side_effect=[0, 901]), \
                 patch.object(suite, 'cancel_own_job') as cancel:
                with self.assertRaisesRegex(RuntimeError, '900 seconds'):
                    suite.execute(argparse.Namespace(run_id=RUN, runtime_root=root))
            self.assertEqual((dest / 'exit-code').read_text(), '1\n')
            cancel.assert_called_once_with(CONFIG, 'ppci-suite-' + RUN, 'only-this-uid')


if __name__ == '__main__':
    unittest.main()
