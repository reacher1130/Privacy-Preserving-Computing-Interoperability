#!/usr/bin/env python3
"""Security and portability boundaries; no Docker, install, or external workload required."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import sys
from unittest.mock import patch

import portable


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableTests(unittest.TestCase):
    def test_bad_download_never_replaces_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'tool.tar.gz'
            dest.write_bytes(b'previous file')
            expected = portable.hashlib.sha256(b'expected download').hexdigest()
            def corrupt_download(*args):
                Path(args[args.index('--output') + 1]).write_bytes(b'corrupt download')
            with patch.object(portable, 'run', side_effect=corrupt_download):
                with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                    portable.fetch('https://example.invalid/tool', dest, expected)
            self.assertEqual(dest.read_bytes(), b'previous file')
            self.assertFalse(dest.with_name(dest.name + '.part').exists())

    def test_private_jdk_is_discoverable_on_a_host_without_system_java(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = Path(tmp) / 'tools'
            java_home = tools / 'jdk21'
            (java_home / 'bin').mkdir(parents=True)
            for name in ('java', 'keytool'):
                binary = java_home / 'bin' / name
                binary.write_text('#!/bin/sh\nexit 0\n')
                binary.chmod(0o755)
            with patch.object(portable, 'TOOLS', tools), patch.dict(portable.os.environ, {'PATH': ''}, clear=True):
                self.assertIsNone(portable.shutil.which('java'))
                environment = portable.environment()
            self.assertEqual(environment['JAVA_HOME'], str(java_home))
            for name in ('java', 'keytool'):
                self.assertEqual(portable.shutil.which(name, path=environment['PATH']), str(java_home / 'bin' / name))

    def test_archive_rejects_escape_and_special_files_before_extracting(self):
        for name, kind, link in (('../secret', tarfile.REGTYPE, ''), ('/absolute', tarfile.REGTYPE, ''),
                                 ('link', tarfile.SYMTYPE, '../../secret'), ('device', tarfile.CHRTYPE, '')):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / 'bad.tar'
                dest = Path(tmp) / 'out'
                with tarfile.open(archive, 'w') as stream:
                    safe = tarfile.TarInfo('safe.txt')
                    safe.size = 2
                    stream.addfile(safe, io.BytesIO(b'ok'))
                    bad = tarfile.TarInfo(name)
                    bad.type = kind
                    bad.linkname = link
                    stream.addfile(bad)
                with self.assertRaises(ValueError):
                    portable.unpack(archive, dest, allow_links=True)
                self.assertFalse((dest / 'safe.txt').exists())

    def test_relative_source_link_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'tracked'
            source.mkdir()
            (source / 'source.txt').write_text('public source')
            (source / 'include').symlink_to('source.txt')
            archive = base / 'source.tar.gz'
            with tarfile.open(archive, 'w:gz') as stream:
                stream.add(source, arcname='source')
            portable.unpack(archive, base / 'dest', allow_links=True)
            self.assertEqual((base / 'dest/source/include').read_text(), 'public source')

    def test_source_export_excludes_ignored_runtime_and_includes_working_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            root.mkdir()
            def git(*args):
                subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init', '-q')
            (root / 'source.py').write_text('original')
            (root / '.gitignore').write_text('private/\n')
            (root / 'private').mkdir()
            (root / 'private/password.json').write_text('DO_NOT_EXPORT')
            git('add', 'source.py', '.gitignore')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture')
            (root / 'source.py').write_text('latest working source')
            archive = Path(tmp) / 'export.tar.gz'
            with patch.object(portable, 'SOURCE', root):
                manifest = portable.source_package(archive)
            self.assertTrue(manifest['dirty'])
            portable.unpack(archive, Path(tmp) / 'out', allow_links=True)
            export = Path(tmp) / 'out/ppci-source'
            self.assertEqual((export / 'source.py').read_text(), 'latest working source')
            self.assertFalse((export / 'private').exists())
            self.assertFalse((export / '.git').exists())
            with patch.object(portable, 'SOURCE', export):
                self.assertEqual(len(list(portable.source_files(export))), 2)
                (export / 'source.py').write_text('tampered')
                with self.assertRaisesRegex(RuntimeError, 'changed'):
                    list(portable.source_files(export))

    def test_release_checksum_failure_never_imports_or_extracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'artifacts.tar.gz').write_bytes(b'corrupt')
            (base / 'source.tar.gz').write_bytes(b'source')
            (base / 'images.tar.gz').write_bytes(b'images')
            (base / 'manifest.json').write_text(json.dumps({'format': 1, 'platform': 'linux/amd64',
                'sha256': {'artifacts.tar.gz': '0' * 64, 'source.tar.gz': portable.digest(base / 'source.tar.gz'),
                           'images.tar.gz': portable.digest(base / 'images.tar.gz')}}))
            with patch.object(portable, 'run') as run, patch.object(portable, 'unpack') as unpack:
                with self.assertRaisesRegex(RuntimeError, 'checksum'):
                    portable.restore(base)
                run.assert_not_called()
                unpack.assert_not_called()

    def test_cidr_must_contain_host(self):
        with self.assertRaises(SystemExit):
            portable.main(['check', '--host', '192.168.1.2', '--lan-cidr', '10.0.0.0/8'])


class PaddleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = load('paddle-smoke')

    def test_authorization_is_bound_to_this_task_file_executor(self):
        task = 'a' * 8 + '-1111-1111-1111-' + 'a' * 12
        auth = 'b' * 8 + '-2222-2222-2222-' + 'b' * 12
        text = f'AuthID: {auth}\nFileID: own-file\nName: TaskID-{task}\nApplier: 1234\nStatus: Unapproved\n'
        self.assertEqual(self.smoke.matching_auths(text, task, 'own-file', '1234'), [auth])
        self.assertEqual(self.smoke.matching_auths(text, task, 'other-file', '1234'), [])
        self.assertEqual(self.smoke.matching_auths(text, 'other-task', 'own-file', '1234'), [])
        self.assertEqual(self.smoke.matching_auths(text, task, 'own-file', 'other-executor'), [])

    def test_predictions_require_exact_unique_ids_and_finite_values(self):
        self.assertEqual(self.smoke.validate_prediction('id,value\na,1\nb,2\n', {'a', 'b'})['rows'], 2)
        for text in ('id,value\na,1\na,2\n', 'id,value\na,nan\nb,2\n', 'id,value\na,1\n'):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                self.smoke.validate_prediction(text, {'a', 'b'})

    def test_partial_upload_resumes_without_recreating_or_reuploading_first_owner(self):
        first = 'aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa'
        second = 'bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb'
        with tempfile.TemporaryDirectory() as tmp:
            argv = ['paddle-smoke.py', '--output', tmp]
            def fail_second(node, operation, *args):
                if operation == 'addns':
                    return 'OK'
                if node == 1:
                    return 'FileID: ' + first
                raise RuntimeError('temporary upload failure')
            with patch.object(sys, 'argv', argv), patch.object(self.smoke, 'owner', side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, 'temporary'):
                    self.smoke.main()
            marker = json.loads((Path(tmp) / 'summary.json').read_text())
            self.assertEqual(marker['files']['train'], [first])
            with patch.object(sys, 'argv', argv), patch.object(self.smoke, 'owner', return_value='FileID: ' + second) as owner, \
                 patch.object(self.smoke, 'requester', side_effect=RuntimeError('stop before publish')):
                with self.assertRaisesRegex(RuntimeError, 'stop before publish'):
                    self.smoke.main()
            self.assertEqual(owner.call_count, 1)
            self.assertEqual(owner.call_args.args[:2], (2, 'upload'))


if __name__ == '__main__':
    unittest.main()
