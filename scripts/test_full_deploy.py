"""Offline checks for deployment boundaries and generated native configuration."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
deploy = load('full_deploy', ROOT / 'scripts/full-deploy.py')


class DeploymentTests(unittest.TestCase):
    def test_bfia_slim_entrypoint_keeps_real_handshake_and_dotted_environment(self):
        entrypoint = ROOT / 'platform/secretflow/interconnection-impl/docker/docker-conf/entrypoint-slim.sh'
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            binary = base / 'ic_main'
            binary.write_text('#!' + sys.executable + '\nimport json, os, sys\n'
                'print(json.dumps({"args": sys.argv[1:], "role": os.environ.get("config.self_role"), '
                '"fields": os.environ.get("runtime.component.parameter.field_names")}))\n'
                'sys.exit(int(os.environ["PPCI_TEST_EXIT"]))\n')
            binary.chmod(0o755)
            wrapper = base / 'entrypoint.sh'
            wrapper.write_text(entrypoint.read_text().replace('/app/ic_main', str(binary)))
            for fields, role, code in [('id', 'host', 0), ('', 'guest', 7)]:
                with self.subTest(fields=fields, role=role):
                    result = subprocess.run(['/bin/bash', str(wrapper)], capture_output=True, text=True,
                        env=dict(os.environ, **{'runtime.component.parameter.algo': 'ecdh_psi',
                            'config.self_role': role, 'runtime.component.parameter.label_owner': 'host',
                            'runtime.component.parameter.field_names': fields, 'system.callback': '',
                            'PPCI_TEST_EXIT': str(code)}))
                    self.assertEqual(result.returncode, code, result.stderr)
                    recorded = json.loads(result.stdout)
                    self.assertEqual(recorded['args'], ['-disable_handshake=0',
                        '-has_label=' + ('true' if role == 'host' else 'false')])
                    self.assertEqual(recorded['role'], role)
                    self.assertEqual(recorded['fields'], '{"host.0":"id","guest.0":"id"}' if fields else '')

    def test_platform_keeps_one_private_signing_key_for_alice_and_bob_across_retries(self):
        provision = load('provision_peer_key', ROOT / 'platform/scripts/environments/provision.py')
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime, units, scripts = base / 'runtime', base / 'units', base / 'runtime/NewProject/scripts'
            units.mkdir()
            java = base / 'jdk/bin/java'
            java.parent.mkdir(parents=True)
            java.touch()
            for repo in ('secretpad', 'secretpad-kimi-upstream'):
                pad = runtime / 'NewProject' / repo
                (pad / 'target').mkdir(parents=True)
                (pad / 'target/secretpad.jar').write_bytes(b'existing jar')
                (pad / 'config').mkdir()
                (pad / 'config/server.jks').write_bytes(b'existing identity')
            for relative in ('secretpad/config/certs', 'secretpad/config/certs/bob-local',
                             'secretpad/config/certs/kimi', 'secretpad-kimi-upstream/config/certs'):
                folder = runtime / 'NewProject' / relative
                folder.mkdir(parents=True, exist_ok=True)
                for name in ('client.crt', 'client.pem', 'token'):
                    (folder / name).write_bytes(b'existing certificate')
            (scripts / 'environments').mkdir(parents=True)
            (scripts / 'environments/portablectl.py').touch()
            def path(value):
                text = str(value)
                if text.startswith('/etc/systemd/system/ppci-'):
                    return units / Path(text).name
                return base / 'ppci-platform' if text == '/usr/local/bin/ppci-platform' else Path(value)
            with patch.object(provision, 'ROOT', runtime), patch.object(provision, 'SCRIPTS', scripts), \
                 patch.object(provision, 'Path', side_effect=path), patch.object(provision, 'run'), \
                 patch.dict(os.environ, {'JAVA_HOME': str(java.parent.parent)}, clear=True), \
                 patch.object(provision.secrets, 'token_hex', return_value='public-unit-test-key') as generate:
                provision.platform()
                key = runtime / 'etc/bfia-peer.env'
                before = key.read_bytes()
                first_units = {p.name: p.read_bytes() for p in units.iterdir()}
                provision.platform()
            generate.assert_called_once_with(32)
            self.assertEqual(key.read_bytes(), before)
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            for node in ('alice', 'bob'):
                unit = (units / f'ppci-{node}.service').read_text()
                self.assertIn('EnvironmentFile=' + str(key) + '\n', unit)
                self.assertNotIn('public-unit-test-key', unit)
            self.assertNotIn('EnvironmentFile=', (units / 'ppci-kimi.service').read_text())
            self.assertEqual({p.name: p.read_bytes() for p in units.iterdir()}, first_units)
            self.assertEqual((runtime / 'NewProject/secretpad/config/server.jks').read_bytes(), b'existing identity')

    def test_native_container_reports_only_an_already_running_ui_for_dns_reload(self):
        native = load('native_ui_reload', ROOT / 'scripts/deploy-paddledtx-full.py')
        for running in (True, False):
            info = {'Config': {'Labels': {'io.ppci.environment': 'portable'}},
                    'Image': 'sha256:owned', 'State': {'Running': running}}
            with patch.object(native, 'call', side_effect=[
                    Mock(returncode=0, stdout=json.dumps([info])),
                    Mock(stdout=json.dumps([{'Id': 'sha256:owned'}])), Mock()]) as call:
                self.assertEqual(native.container('ui', ['image']), running)
                if not running:
                    call.assert_called_with('docker', 'start', 'ui')
        with patch.object(native, 'call', side_effect=[Mock(returncode=1), Mock()]):
            self.assertFalse(native.container('ui', ['image']))

    def test_source_suite_cli_uses_the_selected_python_instead_of_the_system_default(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(deploy, 'Path', return_value=Path(temporary)), \
             patch.object(deploy.sys, 'executable', '/usr/bin/python3.9'), \
             patch.dict(os.environ, PPCI_PYTHON='/usr/bin/python3.6'), patch.object(deploy, 'run') as run:
            deploy.algorithms()
        self.assertEqual(run.call_args_list[0].kwargs['env']['PPCI_PYTHON'], '/usr/bin/python3.9')

    def test_native_executor_build_enables_sqlite_cgo_without_changing_other_binaries(self):
        native = load('native_sqlite_build', ROOT / 'scripts/deploy-paddledtx-full.py')
        environments = {}
        class BuildsCaptured(Exception):
            pass
        def call(*args, **kwargs):
            if args[:2] == ('go', 'build'):
                output = Path(args[args.index('-o') + 1]).name
                if output == 'check-manager':
                    raise BuildsCaptured()
                environments[output] = kwargs['env']['CGO_ENABLED']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = root / 'manager'
            (manager / 'vendor').mkdir(parents=True)
            (manager / 'go.mod').write_text('module baidu/blockchain/dtx-manager\n')
            (manager / 'vendor/modules.txt').write_text('')
            with patch.object(native, 'STAGE', root), patch.object(native, 'sources', return_value=(manager, root / 'frontend', root / 'PaddleDTX')), \
                 patch.object(native, 'call', side_effect=call), patch.dict(os.environ, PPCI_TARGET_ARCH='amd64'), \
                 self.assertRaises(BuildsCaptured):
                native.build()
        self.assertEqual(environments.pop('executor'), '1', 'SQLite must use its real CGO driver')
        self.assertTrue(environments)
        self.assertEqual(set(environments.values()), {'0'})

    def test_fresh_fateboards_leave_the_fixed_kuscia_node_addresses_available(self):
        allocated = {'192.168.117.20', '192.168.117.21'}
        def ensure(name, arguments):
            address = arguments[arguments.index('--ip') + 1] if '--ip' in arguments else next(
                '192.168.117.' + str(i) for i in range(2, 255) if '192.168.117.' + str(i) not in allocated)
            self.assertNotIn(address, allocated)
            allocated.add(address)
        provisioner = Mock()
        provisioner.ensure_container.side_effect = ensure
        with tempfile.TemporaryDirectory() as temporary, patch.object(deploy, 'ROOT', Path(temporary)), \
             patch.object(deploy, 'wait_http'):
            deploy.fateboards(provisioner)
        for address in ('192.168.117.2', '192.168.117.3', '192.168.117.4'):
            self.assertNotIn(address, allocated, 'FATEBoard consumed a later fixed Kuscia node address')

    def test_fresh_engine_import_succeeds_with_only_published_images(self):
        def docker(*args, **kwargs):
            if args[:2] == ('docker', 'save'):
                missing = set(args[4:]) - set(deploy.IMAGES)
                if missing:
                    raise RuntimeError('No such image on fresh host: ' + ','.join(missing))
        with tempfile.TemporaryDirectory() as temporary, patch.object(deploy, 'ROOT', Path(temporary)), \
             patch.object(deploy, 'run', side_effect=docker):
            deploy.import_engines()

    def test_successful_maintainer_build_records_config_id_without_a_registry_digest(self):
        image_id, revision = 'sha256:' + 'a' * 64, 'b' * 40
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            (build / 'tools').mkdir()
            (build / 'tools/bazel-6.5.0').touch()
            def output(command, **kwargs):
                return revision if command[0] == 'git' else json.dumps([{'Id': image_id, 'Architecture': 'amd64'}])
            with patch.object(deploy, 'BUILD', build), patch.object(deploy, 'run'), \
                 patch.object(deploy, 'build_fate'), patch.object(deploy, 'IMAGES', []), \
                 patch.object(deploy.shutil, 'which', return_value='/bin/tool'), \
                 patch.object(deploy.subprocess, 'check_output', side_effect=output):
                deploy.build()
            identity, local = deploy.runtime_identity(build)
            self.assertTrue(local)
            self.assertEqual(identity['source_revision'], revision)
            self.assertEqual(identity['images'][0]['reference'], image_id)
            self.assertFalse((build / 'runtime-release.json').exists())

    def test_deploy_uses_explicit_local_build_flag_only_for_validated_local_image(self):
        image_id = 'sha256:' + 'a' * 64
        identity = {'format': 1, 'kind': 'local-build', 'platform': 'linux/amd64',
                    'runtime_data_included': False, 'source_revision': 'b' * 40,
                    'images': [{'component': 'bfia-suite', 'reference': image_id,
                                'tag': 'ppci/bfia-suite:source-bbbbbbbbbbbb', 'id': image_id}]}
        class HelperReached(Exception):
            pass
        calls = []
        def run(*args, **kwargs):
            calls.append(tuple(map(str, args)))
            if 'scripts/bfia-suite-kuscia.py' in str(args[1]):
                raise HelperReached()
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            deploy.store_runtime_identity(build, identity, local=True)
            with patch.object(deploy, 'BUILD', build), patch.object(deploy, 'preflight'), \
                 patch.object(deploy, 'provisioner'), patch.object(deploy, 'retain_previous_container'), \
                 patch.object(deploy, 'wait_http'), patch.object(deploy, 'fateboards'), \
                 patch.object(deploy, 'run', side_effect=run), patch.object(deploy.subprocess, 'run'), \
                 patch.object(deploy.subprocess, 'check_output', return_value=json.dumps([{'Id': image_id, 'Architecture': 'amd64'}])), \
                 self.assertRaises(HelperReached):
                deploy.deploy({'host': '127.0.0.1', 'lan_cidr': '127.0.0.0/8'}, True)
            self.assertIn('--local-build', calls[-1])
            self.assertEqual(calls[-1][calls[-1].index('--image-ref') + 1], image_id)

    def test_missing_release_metadata_never_initializes_or_restarts_a_runtime(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(deploy, 'BUILD', Path(temporary)), \
             patch.object(deploy, 'preflight'), patch.object(deploy, 'provisioner') as provisioner, \
             patch.object(deploy, 'run') as run, self.assertRaisesRegex(RuntimeError, 'release metadata'):
            deploy.deploy({'host': '127.0.0.1', 'lan_cidr': '127.0.0.0/8'}, False)
        provisioner.assert_not_called()
        run.assert_not_called()

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
