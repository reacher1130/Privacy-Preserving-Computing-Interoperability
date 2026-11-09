#!/usr/bin/env python3
"""Security and portability boundaries; no Docker, install, or external workload required."""
import importlib.util
import io
import json
import os
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
    def test_only_an_empty_containerd_daemon_is_switched_with_configuration_backed_up(self):
        containerd = {'DriverStatus': [['driver-type', 'io.containerd.snapshotter.v1']], 'Containers': 0, 'Images': 0}
        classic = {'DriverStatus': [['Backing Filesystem', 'extfs']], 'Containers': 0, 'Images': 0}
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'daemon.json'
            original = b'{"log-driver":"local","features":{"buildkit":true,"containerd-snapshotter":true}}\n'
            config.write_bytes(original)
            with patch.object(portable, 'DOCKER_DAEMON', config), \
                 patch.object(portable.subprocess, 'check_output', side_effect=[json.dumps(containerd), json.dumps(classic)]), \
                 patch.object(portable, 'run') as run:
                portable.require_classic_docker(prepare_empty=True)
            self.assertEqual(json.loads(config.read_text()), {'log-driver': 'local', 'features': {'buildkit': True, 'containerd-snapshotter': False}})
            backups = list(config.parent.glob('daemon.json.ppci-before-classic-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            run.assert_called_once_with('systemctl', 'restart', 'docker')

    def test_existing_containerd_data_and_readonly_preflight_never_change_the_daemon(self):
        for containers, images, prepare in ((1, 0, True), (0, 1, True), (0, 0, False)):
            with self.subTest(containers=containers, images=images, prepare=prepare), tempfile.TemporaryDirectory() as temporary:
                config = Path(temporary) / 'daemon.json'
                original = b'{"features":{"containerd-snapshotter":true},"log-driver":"local"}'
                config.write_bytes(original)
                info = {'DriverStatus': [['driver-type', 'io.containerd.snapshotter.v1']], 'Containers': containers, 'Images': images}
                with patch.object(portable, 'DOCKER_DAEMON', config), \
                     patch.object(portable.subprocess, 'check_output', return_value=json.dumps(info)), \
                     patch.object(portable, 'run') as run, self.assertRaisesRegex(RuntimeError, 'data is retained'):
                    portable.require_classic_docker(prepare_empty=prepare)
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(list(config.parent.iterdir()), [config])
                run.assert_not_called()

    def test_local_identity_is_distinct_from_published_digest_and_switches_only_owned_metadata(self):
        image_id = 'sha256:' + 'a' * 64
        local = {'format': 1, 'kind': 'local-build', 'platform': 'linux/amd64',
                 'runtime_data_included': False, 'source_revision': 'b' * 40,
                 'images': [{'component': 'bfia-suite', 'reference': image_id,
                             'tag': 'ppci/bfia-suite:source-' + 'b' * 12, 'id': image_id}]}
        published = {'format': 2, 'platform': 'linux/amd64', 'runtime_data_included': False,
                     'sha256': {'artifacts.tar.gz': 'c' * 64},
                     'images': [dict(local['images'][0], reference='ghcr.io/example/suite@sha256:' + 'd' * 64)]}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            portable.store_runtime_identity(directory, local, local=True)
            self.assertEqual(portable.runtime_identity(directory), (local, True))
            with self.assertRaisesRegex(RuntimeError, 'Unsupported prebuilt'):
                portable.validate_prebuilt(local)
            portable.store_runtime_identity(directory, published)
            self.assertFalse((directory / 'runtime-local-build.json').exists())
            self.assertEqual(portable.runtime_identity(directory), (published, False))
            (directory / 'runtime-local-build.json').write_text(json.dumps(local))
            with self.assertRaisesRegex(RuntimeError, 'Conflicting'):
                portable.runtime_identity(directory)
            (directory / 'runtime-local-build.json').write_text('{"owner":"someone-else"}')
            with self.assertRaisesRegex(RuntimeError, 'Invalid local'):
                portable.store_runtime_identity(directory, published)
            self.assertEqual(json.loads((directory / 'runtime-local-build.json').read_text()), {'owner': 'someone-else'})
        for field, value in [('source_revision', 'main'), ('kind', 'published')]:
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, 'Invalid local'):
                portable.validate_local_build(dict(local, **{field: value}))
        for field, value in [('reference', 'ghcr.io/example/suite@' + image_id), ('tag', 'ppci/bfia-suite:latest')]:
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, 'Invalid local'):
                portable.validate_local_build(dict(local, images=[dict(local['images'][0], **{field: value})]))

    def test_offline_local_build_identity_is_restored_without_a_fake_registry_digest(self):
        image_id = 'sha256:' + 'a' * 64
        local = {'format': 1, 'kind': 'local-build', 'platform': 'linux/amd64',
                 'runtime_data_included': False, 'source_revision': 'b' * 40,
                 'images': [{'component': 'bfia-suite', 'reference': image_id,
                             'tag': 'ppci/bfia-suite:source-bbbbbbbbbbbb', 'id': image_id}]}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            package, build = directory / 'package', directory / 'build'
            package.mkdir()
            for name in ('source.tar.gz', 'artifacts.tar.gz', 'images.tar.gz'):
                with tarfile.open(package / name, 'w:gz'):
                    pass
            manifest = {'format': 1, 'platform': 'linux/amd64', 'runtime_data_included': False,
                        'sha256': {p.name: portable.digest(p) for p in package.iterdir()},
                        'images': [{'tag': local['images'][0]['tag'], 'id': image_id}], 'local_build': local}
            (package / 'manifest.json').write_text(json.dumps(manifest))
            with patch.object(portable, 'BUILD', build), patch.object(portable, 'run'), \
                 patch.object(portable, 'require_classic_docker'), \
                 patch.object(portable.subprocess, 'check_output', return_value=image_id):
                portable.restore(package)
            self.assertEqual(portable.runtime_identity(build), (local, True))
            self.assertFalse((build / 'runtime-release.json').exists())

    def test_dnf_runtime_bootstrap_installs_yaml_for_the_selected_interpreter(self):
        for python_name, distro in (('python3.9', 'anolis'), ('python3.11', 'anolis'), ('python3.12', 'rhel')):
            with self.subTest(python=python_name), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                binary = base / 'bin'
                binary.mkdir()
                log = base / 'commands.log'
                def executable(name, body):
                    path = binary / name
                    path.write_text('#!/bin/sh\n' + body)
                    path.chmod(0o755)
                    return path
                executable('id', 'printf "0\\n"\n')
                executable('dnf', 'printf "dnf %s\\n" "$*" >> "$PPCI_INSTALL_TEST_LOG"\n'
                           'case "$*" in *python3.11*) exit 71;; esac\n')
                for name in ('docker', 'systemctl'):
                    executable(name, 'printf "%s %s\\n" "' + name + '" "$*" >> "$PPCI_INSTALL_TEST_LOG"\n')
                executable('dirname', 'value=$1; [ "$value" != -- ] || value=$2; printf "%s\\n" "${value%/*}"\n')
                python = executable(python_name, 'printf "' + python_name + ' %s\\n" "$*" >> "$PPCI_INSTALL_TEST_LOG"\n'
                                    '[ "$1" != -c ] || exit 1\n'
                                    'if [ "$1" = -m ] && [ "$2" = pip ] && [ "$3" = --version ]; then exit 1; fi\n')
                (base / 'systemd').mkdir()
                release = base / 'os-release'
                release.write_text('ID=' + distro + '\nVERSION_ID=' + ('10' if distro == 'rhel' else '8.10') + '\n')
                script = base / 'install-deps.sh'
                text = (Path(portable.SOURCE) / 'scripts/install-deps.sh').read_text()
                script.write_text(text.replace('/run/systemd/system', str(base / 'systemd'))
                                  .replace('. /etc/os-release', '. ' + str(release)))
                subprocess.run(['/bin/bash', str(script)], check=True,
                               env=dict(os.environ, PATH=str(binary), PPCI_PYTHON=str(python), PPCI_INSTALL_TEST_LOG=str(log)))
                commands = log.read_text()
                self.assertIn('python3-pip python3-pyyaml', commands)
                self.assertIn(python_name + ' -m ensurepip --upgrade', commands)
                self.assertIn(python_name + ' -m pip install --only-binary=:all: PyYAML==6.0.3', commands)
                self.assertIn('portable.py install-runtime --native', commands)

    def test_runtime_bootstrap_downloads_only_java_runtime_when_system_rg_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            tools = Path(temporary) / 'tools'
            requests = []
            def metadata(url):
                requests.append(url)
                return json.dumps([{'binary': {'package': {'link': 'https://example.invalid/jre.tar.gz', 'checksum': 'a' * 64}}}])
            def download(url, target, checksum, algorithm):
                self.assertEqual(url, 'https://example.invalid/jre.tar.gz')
                self.assertEqual(checksum, 'a' * 64)
                with tarfile.open(target, 'w:gz') as stream:
                    for name in ('java', 'keytool'):
                        item = tarfile.TarInfo('jre21/bin/' + name)
                        item.size = 1
                        item.mode = 0o755
                        stream.addfile(item, io.BytesIO(b'x'))
            with patch.object(portable, 'TOOLS', tools), patch.object(portable.platform, 'machine', return_value='x86_64'), \
                 patch.object(portable, 'url_text', side_effect=metadata), patch.object(portable, 'fetch', side_effect=download), \
                 patch.object(portable.shutil, 'which', return_value='/usr/bin/rg'), patch.object(portable, 'run') as run:
                portable.install_tools(runtime_only=True)
            self.assertEqual(len(requests), 1)
            self.assertIn('image_type=jre', requests[0])
            self.assertTrue((tools / 'jdk21/bin/keytool').is_file())
            self.assertFalse((tools / 'jdk21/bin/javac').exists())
            self.assertFalse(any((tools / name).exists() for name in ('go124', 'node20', 'maven', 'pnpm8')))
            run.assert_not_called()

    def test_default_all_restores_prebuilt_release_and_never_builds(self):
        with patch.object(portable.platform, 'system', return_value='Linux'), \
             patch.object(portable.platform, 'machine', return_value='x86_64'), \
             patch.object(portable.os, 'geteuid', return_value=0), \
             patch.object(portable, 'environment', return_value={}), \
             patch.object(portable, 'prebuilt_release') as release, patch.object(portable, 'run') as run:
            portable.main(['all', '--no-tests'])
        release.assert_called_once()
        calls = [list(map(str, call.args)) for call in run.call_args_list]
        self.assertEqual(calls[0][-1], 'runtime')
        self.assertFalse(any('build' in call for call in calls))
        self.assertFalse(any('submodule' in call for call in calls))
        self.assertEqual([call[2] for call in calls[1:]], ['preflight', 'preflight', 'deploy', 'status'])

    def test_launcher_ignores_old_system_python_when_supported_python_is_available(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            old = base / 'python3'
            old.write_text('#!/bin/sh\nexit 1\n')
            unsupported = base / 'python3.12'
            unsupported.write_text('#!/bin/sh\nexit 1\n')
            selected = base / 'python3.11'
            selected.write_text('#!/bin/sh\n[ "$1" != -c ] || exit 0\nprintf "%s\\n" "$PPCI_PYTHON"\n')
            for path in (old, unsupported, selected):
                path.chmod(0o755)
            environment = dict(os.environ, PATH=str(base) + ':' + os.environ.get('PATH', ''), PPCI_PYTHON=str(old))
            result = subprocess.check_output(['/bin/bash', str(Path(portable.SOURCE) / 'deploy.sh'), '--help'],
                                             env=environment, text=True)
            self.assertEqual(result.strip(), str(selected))

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


class PrebuiltReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.archive = self.base / 'artifacts.tar.gz'
        self.build = self.base / 'build'
        self.artifacts = ('component/program',)
        with tarfile.open(self.archive, 'w:gz') as stream:
            entry = tarfile.TarInfo(self.artifacts[0])
            entry.size = 2
            stream.addfile(entry, io.BytesIO(b'ok'))
        self.manifest = {'format': 2, 'platform': 'linux/amd64', 'runtime_data_included': False,
                         'sha256': {'artifacts.tar.gz': portable.digest(self.archive)},
                         'images': [{'component': 'bfia-suite', 'reference': 'ghcr.io/example/suite@sha256:' + 'a' * 64,
                                     'tag': 'ghcr.io/example/suite:v1', 'id': 'sha256:' + 'b' * 64}]}

    def restore(self):
        with patch.object(portable, 'BUILD', self.build), patch.object(portable, 'ARTIFACTS', self.artifacts):
            portable.restore_prebuilt(self.base, self.manifest)

    def test_verified_release_pulls_by_digest_and_retains_required_local_tag(self):
        image = self.manifest['images'][0]
        self.build.mkdir()
        portable.store_runtime_identity(self.build, {'format': 1, 'kind': 'local-build', 'platform': 'linux/amd64',
            'runtime_data_included': False, 'source_revision': 'c' * 40,
            'images': [dict(image, reference=image['id'])]}, local=True)
        with patch.object(portable, 'run') as run, \
             patch.object(portable.subprocess, 'check_output', return_value=json.dumps([{'Architecture': 'amd64', 'Id': image['id']}]).encode()):
            self.restore()
        self.assertEqual((self.build / self.artifacts[0]).read_bytes(), b'ok')
        self.assertEqual(run.call_args_list[0].args, ('docker', 'pull', '--platform', 'linux/amd64', image['reference']))
        self.assertEqual(run.call_args_list[1].args, ('docker', 'tag', image['reference'], image['tag']))
        self.assertEqual(json.loads((self.build / 'runtime-release.json').read_text()), self.manifest)
        self.assertFalse((self.build / 'runtime-local-build.json').exists())

    def test_bad_checksum_or_unpinned_image_never_imports_or_extracts(self):
        for field in ('checksum', 'reference'):
            with self.subTest(field=field):
                value = json.loads(json.dumps(self.manifest))
                if field == 'checksum':
                    value['sha256']['artifacts.tar.gz'] = '0' * 64
                else:
                    value['images'][0]['reference'] = 'ghcr.io/example/suite:latest'
                with patch.object(portable, 'run') as run, patch.object(portable, 'unpack') as unpack, \
                     patch.object(portable, 'BUILD', self.build), self.assertRaises(RuntimeError):
                    portable.restore_prebuilt(self.base, value)
                run.assert_not_called()
                unpack.assert_not_called()

    def test_unmanaged_existing_artifact_is_not_replaced(self):
        target = self.build / self.artifacts[0]
        target.parent.mkdir(parents=True)
        target.write_bytes(b'keep local build')
        with patch.object(portable, 'run') as run, self.assertRaisesRegex(RuntimeError, 'unmanaged'):
            self.restore()
        self.assertEqual(target.read_bytes(), b'keep local build')
        run.assert_not_called()

    def test_parent_symlink_does_not_redirect_promotion_outside_build(self):
        self.build.mkdir()
        outside = self.base / 'outside'
        outside.mkdir()
        (self.build / 'component').symlink_to(outside, target_is_directory=True)
        (self.build / '.ppci-prebuilt-artifacts').write_text('PPCI prebuilt artifacts\n')
        with patch.object(portable, 'run') as run, self.assertRaisesRegex(RuntimeError, 'symbolic-link'):
            self.restore()
        run.assert_not_called()
        self.assertFalse((outside / 'program').exists())

    def test_release_pin_and_artifact_hashes_are_used_for_download(self):
        source = self.base / 'source'
        (source / 'releases').mkdir(parents=True)
        manifest_bytes = json.dumps(self.manifest).encode()
        checksum = portable.hashlib.sha256(manifest_bytes).hexdigest()
        url = 'https://example.invalid/releases/v1/manifest.json'
        (source / 'releases/runtime.json').write_text(json.dumps({'format': 1, 'manifest_url': url, 'sha256': checksum}))
        def download(address, target, expected):
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.name == 'manifest.json':
                self.assertEqual((address, expected), (url, checksum))
                target.write_bytes(manifest_bytes)
            else:
                self.assertEqual((address, expected), ('https://example.invalid/releases/v1/artifacts.tar.gz', self.manifest['sha256']['artifacts.tar.gz']))
                target.write_bytes(self.archive.read_bytes())
        with patch.object(portable, 'SOURCE', source), patch.object(portable, 'BUILD', self.build), \
             patch.object(portable, 'fetch', side_effect=download) as fetch, patch.object(portable, 'restore_prebuilt') as restore:
            portable.prebuilt_release()
        self.assertEqual(fetch.call_count, 2)
        restore.assert_called_once_with(self.build / 'releases' / checksum, self.manifest)


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
