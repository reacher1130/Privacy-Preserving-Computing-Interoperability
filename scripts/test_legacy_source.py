import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('legacy_source', Path(__file__).with_name('prepare-legacy-source.py'))
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


class LegacySourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'source.tar.gz'
        self.manifest = self.root / 'source.json'
        for name, value in [('ARCHIVE', self.archive), ('MANIFEST', self.manifest)]:
            change = patch.object(legacy, name, value)
            change.start()
            self.addCleanup(change.stop)

    def fixture(self, members=None):
        members = members or [('dtx-manager/main.go', b'package main\n', None)]
        with tarfile.open(self.archive, 'w:gz') as archive:
            for name, data, link in members:
                info = tarfile.TarInfo(name)
                if link is None:
                    info.size, info.mode = len(data), 0o644
                    archive.addfile(info, io.BytesIO(data))
                else:
                    info.type, info.linkname = tarfile.SYMTYPE, link
                    archive.addfile(info)
        record = {'format': 1, 'sha256': hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                  'files': len(members), 'source_bytes': sum(len(data) for _, data, link in members if link is None)}
        self.manifest.write_text(json.dumps(record))
        return record

    def test_build_source_and_vendor_logs_are_retained(self):
        allowed = [('dtx-manager', 'main.go'), ('dtx-manager', 'config/config.go'),
                   ('dtx-manager', 'vendor/github.com/beego/beego/v2/core/logs/log.go'),
                   ('dtx-fe', 'src/pages/index.tsx'), ('dtx-fe', 'package-lock.json'),
                   ('PaddleDTX', 'dai/executor/config/config.go'), ('PaddleDTX', 'dai/vendor/pkg/LICENSE'),
                   ('PaddleDTX', 'LICENSE')]
        for module, path in allowed:
            with self.subTest(module=module, path=path):
                self.assertTrue(legacy.included(module, path))

    def test_deployment_identities_caches_tests_and_compiled_outputs_are_excluded(self):
        denied = [('unknown', 'main.go'), ('dtx-manager', 'conf/app.conf'),
                  ('dtx-manager', 'controllers/auth_test.go'), ('dtx-manager', 'models/private.pem'),
                  ('dtx-manager', 'models/private.key'), ('dtx-manager', 'models/events.log'),
                  ('dtx-manager', 'models/runtime.sqlite-wal'), ('dtx-manager', 'models/runtime.sqlite3'),
                  ('dtx-manager', 'models/runtime.mv.db'), ('dtx-manager', 'models/runtime.trace.db'),
                  ('dtx-manager', 'config/.env.local'), ('dtx-manager', 'models/../../private.go'),
                  ('dtx-manager', '/main.go'),
                  ('dtx-manager', 'models/.git/config'), ('dtx-manager', 'models/__pycache__/a.pyc'),
                  ('dtx-fe', 'src/node_modules/a.js'), ('dtx-fe', 'src/client.p12'),
                  ('dtx-fe', 'build/index.html'), ('PaddleDTX', 'dai/conf/config.toml'),
                  ('PaddleDTX', 'dai/testdata/keys/private.key'), ('PaddleDTX', 'dai/bin/executor'),
                  ('PaddleDTX', 'dai/output/result.csv'), ('PaddleDTX', 'dai/executor.local')]
        for module, path in denied:
            with self.subTest(module=module, path=path):
                self.assertFalse(legacy.included(module, path))

    def test_retired_deployment_notes_are_removed_without_changing_source(self):
        original = 'package baas\nfunc Keep() {}\n// 获取验证码\n//fetch secret-deployment-note\n'.encode()
        result = legacy.sanitize('dtx-manager', 'handlers/baas/baas.go', original)
        self.assertEqual(result, b'package baas\nfunc Keep() {}\n')
        self.assertEqual(legacy.sanitize('dtx-manager', 'main.go', original), original)
        development = b"proxy: {\n// target: 'http://old-host'\ntarget: 'http://private-host:1234'\n}\n"
        result = legacy.sanitize('dtx-fe', 'scripts/webpack.dev.js', development)
        self.assertIn(b"target: 'http://127.0.0.1:18088'", result)
        self.assertNotIn(b'old-host', result)
        self.assertNotIn(b'private-host', result)

    def test_obsolete_baas_jump_is_removed_from_source_snapshot(self):
        source = ("import { useCallback, useState } from 'react';\n  getJumpToken,\n"
                  "import Button from '@/components/Button';\n"
                  "  const openBass = useCallback(() => {\n    getJumpToken();\n  });\n"
                  "  return (\n        {\n          <Button onClick={openBass}/>\n        }\n"
                  "        <Row>keep blockchain information</Row>\n  );\n").encode()
        result = legacy.sanitize('dtx-fe', 'src/views/Operation/Blockchain/index.tsx', source)
        self.assertNotIn(b'getJumpToken', result)
        self.assertNotIn(b'openBass', result)
        self.assertNotIn(b'useCallback', result)
        self.assertIn(b'keep blockchain information', result)

    def test_valid_snapshot_extracts_only_declared_source(self):
        record = self.fixture([('dtx-manager/main.go', b'package main\n', None),
                               ('dtx-fe/src/app.ts', b'export {}\n', None)])
        target = self.root / 'build'
        self.assertEqual(legacy.extract(target), record)
        self.assertEqual((target / 'dtx-manager/main.go').read_bytes(), b'package main\n')
        self.assertEqual((target / 'dtx-fe/src/app.ts').stat().st_mode & 0o777, 0o644)

    def test_checksum_mismatch_does_not_create_output(self):
        self.fixture()
        self.archive.write_bytes(self.archive.read_bytes() + b'changed')
        target = self.root / 'build'
        with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
            legacy.extract(target)
        self.assertFalse(target.exists())

    def test_member_count_size_and_duplicate_paths_fail_before_extraction(self):
        for mutation in ('count', 'size', 'duplicate'):
            with self.subTest(mutation=mutation):
                members = [('dtx-manager/main.go', b'x', None)]
                record = self.fixture(members * (2 if mutation == 'duplicate' else 1))
                if mutation == 'count':
                    record['files'] += 1
                if mutation == 'size':
                    record['source_bytes'] += 1
                self.manifest.write_text(json.dumps(record))
                target = self.root / ('build-' + mutation)
                with self.assertRaisesRegex(RuntimeError, 'member count mismatch'):
                    legacy.extract(target)
                self.assertFalse(target.exists())

    def test_traversal_links_and_non_source_members_fail_before_extraction(self):
        attacks = [('../../escape.go', b'x', None), ('/tmp/escape.go', b'x', None),
                   ('dtx-manager/controllers/../../../escape.go', b'x', None),
                   ('dtx-manager/main.go', b'', '/etc/passwd'), ('dtx-manager/conf/app.conf', b'secret', None),
                   ('PaddleDTX/dai/conf/config.toml', b'secret', None)]
        for index, attack in enumerate(attacks):
            with self.subTest(attack=attack):
                self.fixture([attack])
                target = self.root / ('build-' + str(index))
                with self.assertRaisesRegex(RuntimeError, 'Unexpected source archive member'):
                    legacy.extract(target)
                self.assertFalse(target.exists())

    def test_nonempty_destination_is_never_overwritten(self):
        self.fixture()
        target = self.root / 'build'
        target.mkdir()
        valuable = target / 'keep'
        valuable.write_bytes(b'original')
        with self.assertRaisesRegex(RuntimeError, 'empty build directory'):
            legacy.extract(target)
        self.assertEqual(valuable.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
