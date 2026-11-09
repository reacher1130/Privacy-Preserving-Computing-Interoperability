"""Offline checks for deployment boundaries and generated native configuration."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
deploy = load('full_deploy', ROOT / 'scripts/full-deploy.py')


class DeploymentTests(unittest.TestCase):
    def test_fixed_subnets_reject_lan_or_other_docker_routes(self):
        deploy.validate_routes([{'dst': 'default', 'dev': 'eth0'}, {'dst': '0.0.0.0/0', 'dev': 'eth0'},
                                {'dst': '192.168.45.0/24', 'dev': 'eth0'}], [])
        with self.assertRaisesRegex(RuntimeError, 'Host route'):
            deploy.validate_routes([{'dst': '192.168.117.0/24', 'dev': 'eth0'}], [])
        with self.assertRaisesRegex(RuntimeError, 'Host route'):
            deploy.validate_routes([{'dst': '192.168.117.0/24'}], [])
        own = {'Name': 'kuscia-exchange', 'Id': '1234567890abcdef', 'IPAM': {'Config': [{'Subnet': '192.168.117.0/24'}]}}
        deploy.validate_routes([{'dst': '192.168.117.0/24', 'dev': 'br-1234567890ab'}], [own])
        own['Options'] = {'com.docker.network.bridge.name': 'ppci-bridge'}
        deploy.validate_routes([{'dst': '192.168.117.0/24', 'dev': 'ppci-bridge'}], [own])
        with self.assertRaisesRegex(RuntimeError, 'Host route'):
            deploy.validate_routes([{'dst': '192.168.0.0/16', 'dev': 'vpn0'}], [own])
        other = {'Name': 'another-stack', 'IPAM': {'Config': [{'Subnet': '172.31.0.0/16'}]}}
        with self.assertRaisesRegex(RuntimeError, 'Another Docker network'):
            deploy.validate_routes([], [other])
        own['IPAM']['Config'][0]['Subnet'] = '10.10.0.0/24'
        with self.assertRaisesRegex(RuntimeError, 'unexpected subnet'):
            deploy.validate_routes([], [own])

    def test_network_boundaries(self):
        self.assertEqual(deploy.configuration('127.0.0.1', '127.0.0.0/8')['host'], '127.0.0.1')
        self.assertEqual(deploy.configuration('192.168.45.101', None)['lan_cidr'], '192.168.45.0/24')
        for host, cidr in [('8.8.8.8', None), ('192.168.45.101', '0.0.0.0/0'),
                           ('192.168.45.101', '10.0.0.0/24'), ('127.0.0.1\nallow all;', None)]:
            with self.subTest(host=host, cidr=cidr), self.assertRaises(ValueError):
                deploy.configuration(host, cidr)
        with patch.object(deploy, 'BUILD', deploy.SOURCE / 'build'), self.assertRaises(ValueError):
            deploy.configuration('127.0.0.1', None)

    def test_arm_requires_vm_before_any_host_mutation(self):
        with patch.object(deploy.platform, 'machine', return_value='aarch64'), \
             patch.object(deploy.platform, 'system', return_value='Linux'), \
             patch.object(deploy, 'run') as run, self.assertRaisesRegex(RuntimeError, 'VM'):
            deploy.preflight()
        run.assert_not_called()

    def test_fate_build_includes_reviewed_parser_and_six_classes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, build = Path(temporary) / 'source', Path(temporary) / 'build'
            board = source / 'platform/fate/fate_board/src/main/java/org/fedai/fate/board'
            for name in ('websocket/JobWebSocketController.java', 'services/JobWebSocketService.java',
                         'controller/JobManagerController.java', 'services/JobDetailService.java',
                         'websocket/LogWebSocketController.java', 'controller/JobDetailController.java'):
                target = board / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / target.relative_to(source), target)
            parser = source / 'platform/fate/fate_flow/python/fate_flow/controller/parser.py'
            parser.parent.mkdir(parents=True)
            shutil.copy2(ROOT / parser.relative_to(source), parser)
            patches = source / 'platform/patches/fate'
            patches.mkdir(parents=True)
            for name in ('flow.patch', 'board-string-party-id.patch'):
                shutil.copy2(ROOT / 'platform/patches/fate' / name, patches / name)
            original_parser = parser.read_bytes()
            original_board = {path: path.read_bytes() for path in board.rglob('*.java')}
            with patch.object(deploy, 'SOURCE', source), patch.object(deploy, 'BUILD', build), \
                 patch.object(deploy, 'run') as run:
                deploy.build_fate()
            recipe = (build / 'fate-image/Dockerfile').read_text()
            self.assertIn('jdk-8u345/bin/javac', recipe)
            self.assertIn('jar uf fateboard-2.1.0.jar', recipe)
            self.assertNotIn('auth-disabled', recipe)
            self.assertEqual(len(list((build / 'fate-image/sources').glob('*.java'))), 6)
            self.assertIn('"task_cores": max(1, int(self.engine_run.get("cores") or 1))',
                          (build / 'fate-image/parser.py').read_text())
            self.assertIn('String partyId', (build / 'fate-image/sources/JobWebSocketService.java').read_text())
            self.assertEqual(parser.read_bytes(), original_parser)
            self.assertTrue(all(path.read_bytes() == content for path, content in original_board.items()))
            run.assert_called_once_with('docker', 'build', '-t', deploy.FATE_IMAGE, build / 'fate-image')
            # A Gitless export may already contain the reviewed working patches.
            shutil.copy2(build / 'fate-image/parser.py', parser)
            for path in original_board:
                shutil.copy2(build / 'fate-image/sources' / path.name, path)
            patched_parser = parser.read_bytes()
            with patch.object(deploy, 'SOURCE', source), patch.object(deploy, 'BUILD', build), patch.object(deploy, 'run'):
                deploy.build_fate()
            self.assertEqual(parser.read_bytes(), patched_parser)

    def test_gateway_acl_boards_websocket_and_native_routes(self):
        provision = load('provision_test', ROOT / 'platform/scripts/environments/provision.py')
        original_path = Path
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            conf = directory / 'nginx.conf'
            def mapped_path(value):
                return conf if str(value) == '/etc/nginx/conf.d/ppci.conf' else original_path(value)
            with patch.object(provision, 'ROOT', directory / 'runtime'), \
                 patch.object(provision, 'BUILD', directory / 'build'), \
                 patch.object(provision, 'Path', side_effect=mapped_path), \
                 patch.object(provision, 'run'), patch.object(provision.subprocess, 'run') as process, \
                 patch.dict(os.environ, PPCI_FATE_EXTERNAL_BOARD='1', PPCI_NATIVE_UI_PORT='18088'):
                process.return_value.returncode = 1
                provision.gateway({'host': '127.0.0.1', 'lan_cidr': '127.0.0.0/8'})
            text = conf.read_text()
            self.assertEqual(text.count('  listen '), 6)
            self.assertEqual(text.count('allow 127.0.0.0/8;\n  deny all;'), 6)
            self.assertIn('127.0.0.1:19483', text)
            self.assertIn('127.0.0.1:19484', text)
            self.assertEqual(text.count('proxy_set_header Upgrade $http_upgrade;'), 2)
            self.assertIn('location /dtx/v1/ { proxy_pass http://127.0.0.1:18088;', text)
            self.assertIn(str(directory / 'runtime/NewProject/secretpad-frontend-dist-e2e'), text)

    def test_pinned_spu_exports_without_git_history(self):
        builder = load('bfia_builder', ROOT / 'platform/scripts/environments/build-bfia.py')
        with tempfile.TemporaryDirectory() as temporary, patch.object(builder, 'SOURCE', ROOT):
            destination = builder.pinned_spu(Path(temporary))
            self.assertTrue((destination / 'WORKSPACE').is_file())
            self.assertTrue((destination / 'LICENSE').is_file())
            self.assertFalse((destination / '.git').exists())
            with patch.object(builder.shutil, 'rmtree') as remove:
                self.assertEqual(builder.pinned_spu(Path(temporary)), destination)
                remove.assert_not_called()


if __name__ == '__main__':
    unittest.main()
