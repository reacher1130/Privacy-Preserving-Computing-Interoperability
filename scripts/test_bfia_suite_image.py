"""Small offline checks for the self-contained image's source and result boundaries."""
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = '01234567-89ab-cdef-0123-456789abcdef'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'images/bfia-suite' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entry = load('bfia_suite_entrypoint', 'entrypoint.py')
context = load('bfia_suite_context', 'prepare-context.py')


class SuiteImageTests(unittest.TestCase):
    def test_run_identifier_never_accepts_a_path(self):
        self.assertEqual(entry.arguments([RUN_ID]).run_id, RUN_ID)
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            for value in ('../escape', '/absolute', RUN_ID.upper()):
                with self.subTest(identifier=value), self.assertRaises(SystemExit):
                    entry.arguments([value])

    def test_output_rejects_traversal_symlinks_and_reused_results(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            directory = Path(temporary)
            for value in ('/', 'relative', str(directory / '../other')):
                with self.subTest(path=value), self.assertRaises(ValueError):
                    entry.output_directory(value, RUN_ID)
            (directory / 'alias').symlink_to(directory, target_is_directory=True)
            with self.assertRaises(ValueError):
                entry.output_directory(str(directory / 'alias/out'), RUN_ID)
            output = entry.output_directory(str(directory / 'result'), RUN_ID)
            (output / 'exit-code').write_text('0\n')
            with self.assertRaises(ValueError):
                entry.output_directory(str(output), RUN_ID)

    def test_success_requires_all_eight_numerical_and_protocol_results(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            output = Path(temporary)
            for language, names in (('python', entry.PYTHON), ('cpp', entry.CPP)):
                directory = output / language / RUN_ID
                directory.mkdir(parents=True)
                for kind in ('numerical', 'protocol'):
                    values = {name: {'pass': True} for name in names}
                    if language == 'cpp' and kind == 'numerical':
                        values['ss-vif']['pass'] = 'true'
                    (directory / (kind + '-validation.json')).write_text(json.dumps(values))
            result = entry.report(output, RUN_ID, {'python': 0, 'cpp': 0})
            self.assertEqual(result['status'], 'FAILED')
            self.assertEqual(len(result['algorithms']), 8)
            self.assertEqual((output / 'exit-code').read_text(), '1\n')
            (output / 'report.json').unlink()
            (output / 'exit-code').unlink()
            file = output / 'cpp' / RUN_ID / 'numerical-validation.json'
            values = json.loads(file.read_text()); values['ss-vif']['pass'] = True
            file.write_text(json.dumps(values))
            self.assertEqual(entry.report(output, RUN_ID, {'python': 0, 'cpp': 0})['status'], 'PASSED')

    def test_bundle_preserves_public_results_but_excludes_links_and_environment(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            output = Path(temporary)
            directory = output / 'cpp' / RUN_ID / 'ss-lr'
            directory.mkdir(parents=True)
            (directory / 'alice.log').write_text('actual computation\n')
            (directory / 'alice.env').write_text('do not include environment\n')
            (directory / 'bob.log').symlink_to('/etc/hosts')
            (output / 'report.json').write_text('{}')
            (output / 'exit-code').write_text('1\n')
            payload = entry.bundle(output, RUN_ID)
            with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
                names = archive.getnames()
                self.assertIn(f'cpp/{RUN_ID}/ss-lr/alice.log', names)
                self.assertFalse(any(name.endswith(('.env', 'bob.log')) for name in names))
                self.assertTrue(all(member.isfile() for member in archive))
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                entry.frames('BUNDLE', RUN_ID, payload)
            lines = captured.getvalue().splitlines()
            self.assertEqual(lines[0], f'PPCI_BFIA_BUNDLE_BEGIN {RUN_ID} {hashlib.sha256(payload).hexdigest()} {len(payload)}')
            self.assertTrue(all(len(line) < 4200 for line in lines))
            encoded = ''.join(line.split()[1] for line in lines if line.startswith('PPCI_BFIA_BUNDLE_DATA '))
            self.assertEqual(base64.b64decode(encoded), payload)
            self.assertEqual(lines[-1], f'PPCI_BFIA_BUNDLE_END {RUN_ID}')
            with patch.object(entry, 'MAX_UNCOMPRESSED', 1), self.assertRaises(ValueError):
                entry.bundle(output, RUN_ID)

    def test_atomic_report_does_not_follow_an_existing_temporary_symlink(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            directory = Path(temporary)
            victim = directory / 'preserved'; victim.write_text('keep')
            (directory / 'report.json.tmp').symlink_to(victim)
            with self.assertRaises(FileExistsError):
                entry.write_atomic(directory / 'report.json', b'change')
            self.assertEqual(victim.read_text(), 'keep')

    def test_live_log_snapshot_is_bounded_and_only_sent_when_changed(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            output = Path(temporary)
            directory = output / 'python' / RUN_ID / 'sgb'; directory.mkdir(parents=True)
            log = directory / 'alice.stdout.log'; log.write_bytes(b'x' * (70 * 1024))
            sent = {}; captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                entry.snapshots(output, RUN_ID, sent)
                entry.snapshots(output, RUN_ID, sent)
            lines = captured.getvalue().splitlines()
            self.assertEqual(sum(line.startswith('PPCI_BFIA_FILE_BEGIN') for line in lines), 1)
            self.assertTrue(lines[0].endswith('65536'))
            encoded = ''.join(line.split()[1] for line in lines if line.startswith('PPCI_BFIA_FILE_DATA '))
            self.assertEqual(base64.b64decode(encoded), b'x' * 65536)

    def test_group_preserves_python_libraries_but_cannot_use_a_host_docker_daemon(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary, \
             patch.dict(os.environ, {'LD_LIBRARY_PATH': '/tested-python-libraries', 'DOCKER_HOST': 'ssh://not-used',
                                     'BFIA_CPP_ALGOS': 'one-algorithm'}, clear=True), \
             patch.object(entry.subprocess, 'Popen') as launch, contextlib.redirect_stdout(io.StringIO()):
            process = launch.return_value; process.poll.return_value = 0; process.returncode = 0
            self.assertEqual(entry.run_group('cpp', 'run_audited_cpp_tests.sh', Path(temporary), RUN_ID, False, {}), 0)
            environment = launch.call_args.kwargs['env']
            self.assertEqual(environment['LD_LIBRARY_PATH'], '/tested-python-libraries')
            self.assertEqual(environment['BFIA_CPP_RUNTIME'], 'binary')
            self.assertEqual(environment['BFIA_CPP_ALGOS'], ','.join(entry.CPP))
            self.assertNotIn('DOCKER_HOST', environment)

    def test_context_includes_only_pinned_source_and_required_licenses(self):
        def git(directory, *args):
            return subprocess.check_output(['git', '-C', str(directory), *args], stderr=subprocess.DEVNULL)
        with tempfile.TemporaryDirectory(dir='/private/tmp') as temporary:
            source = Path(temporary) / 'checkout'; source.mkdir()
            repo = source / 'platform/secretflow'; repo.mkdir(parents=True)
            git(source, 'init'); git(repo, 'init')
            required = ['secretflow/__init__.py', 'secretflow/version.py', 'bfia/sgb/alice.py',
                        'bfia/he_woe/bob.py', 'bfia/run_cpp_tests.sh', 'bfia/validate_numerics.py',
                        'interconnection/interconnection/__init__.py', 'LICENSE', 'interconnection/LICENSE']
            excluded = ['bfia/results/old.log', 'secretflow/private.pem', 'interconnection-impl/private_key.pem']
            for name in required + excluded:
                path = repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# fixture\n')
            git(repo, 'add', '.')
            git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-m', 'fixture')
            git(source, 'add', 'platform/secretflow')
            git(source, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-m', 'pin')
            recipe = source / 'images/bfia-suite'; recipe.mkdir(parents=True)
            for name in ('Dockerfile', 'entrypoint.py', 'ic-main.sh'): (recipe / name).write_text('# recipe\n')
            tools = Path(temporary) / 'tools'; tools.mkdir()
            rg = tools / 'rg'; rg.write_bytes(b'\x7fELF\x02\x01' + b'\0' * 12 + b'\x3e\0')
            for name in ('LICENSE-MIT', 'UNLICENSE'): (tools / name).write_text('fixture license\n')
            output = Path(temporary) / 'image-context'
            manifest = context.prepare(source, output, rg)
            self.assertEqual(set(manifest['files']), set(required))
            self.assertTrue((output / 'licenses/ripgrep-LICENSE-MIT').is_file())
            self.assertFalse((output / '.git').exists())
            with self.assertRaises(RuntimeError): context.prepare(source, output, rg)
            (repo / 'secretflow/version.py').write_text('uncommitted\n')
            with self.assertRaisesRegex(RuntimeError, 'Uncommitted'):
                context.prepare(source, Path(temporary) / 'other-context', rg)


if __name__ == '__main__':
    unittest.main()
