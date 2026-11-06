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


spec = importlib.util.spec_from_file_location('amd64_vm', Path(__file__).with_name('amd64-vm.py'))
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class VmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def options(self, *args):
        return vm.parser().parse_args(['--state-dir', str(self.root / 'vm'), *args])

    def archive(self, items):
        path = self.root / 'source.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, kind, target in [('ppci-source/deploy.sh', 'file', ''), *items]:
                info = tarfile.TarInfo(name)
                if kind == 'sym':
                    info.type, info.linkname = tarfile.SYMTYPE, target
                    archive.addfile(info)
                elif kind == 'hard':
                    info.type, info.linkname = tarfile.LNKTYPE, target
                    archive.addfile(info)
                else:
                    info.size = 1
                    archive.addfile(info, io.BytesIO(b'x'))
        return path

    def test_official_checksum_selects_exact_filename(self):
        good = 'a' * 64
        self.assertEqual(vm.checksum_for(good + ' *' + vm.IMAGE_NAME + '\n'), good)
        for data in ('', good + ' other.img', (good + ' ' + vm.IMAGE_NAME + '\n') * 2):
            with self.assertRaises(RuntimeError):
                vm.checksum_for(data)

    def test_cached_base_image_reused_without_network(self):
        self.root.joinpath(vm.IMAGE_NAME).write_bytes(b'cached-image')
        self.root.joinpath('base-image.sha256').write_text(hashlib.sha256(b'cached-image').hexdigest())
        with patch.object(vm.urllib.request, 'urlopen', side_effect=AssertionError('must remain offline')):
            self.assertEqual(vm.image(self.root), self.root / vm.IMAGE_NAME)
        self.root.joinpath(vm.IMAGE_NAME).write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
            vm.image(self.root)

    def test_download_mismatch_never_creates_base_or_disk(self):
        with patch.object(vm.urllib.request, 'urlopen', side_effect=[
                io.BytesIO(('a' * 64 + ' ' + vm.IMAGE_NAME).encode()), io.BytesIO(b'wrong')]):
            with self.assertRaisesRegex(RuntimeError, 'SHA256 mismatch'):
                vm.image(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_local_base_requires_checksum_and_does_not_download(self):
        source = self.root / 'offline.img'
        source.write_bytes(b'offline')
        with self.assertRaisesRegex(RuntimeError, 'requires --base-image-sha256'):
            vm.image(self.root, source)
        with patch.object(vm.urllib.request, 'urlopen', side_effect=AssertionError('offline')):
            target = vm.image(self.root, source, vm.sha256(source))
        self.assertEqual(target.read_bytes(), b'offline')

    def test_cloud_seed_locks_password_and_only_uses_local_public_key(self):
        data = json.loads(vm.cloud_config('ssh-ed25519 YWJj test').split('\n', 1)[1])
        self.assertFalse(data['ssh_pwauth'])
        self.assertTrue(data['disable_root'])
        self.assertTrue(data['users'][0]['lock_passwd'])
        self.assertEqual(data['users'][0]['ssh_authorized_keys'], ['ssh-ed25519 YWJj test'])
        with self.assertRaises(RuntimeError):
            vm.cloud_config('ssh-ed25519 abc\nusers: []')

    def test_qemu_is_amd64_tcg_and_api_ports_are_not_forwarded(self):
        config = vm.settings(self.options('start'))
        args = vm.qemu_command(config)
        self.assertIn('q35,accel=tcg', args)
        net = args[args.index('-netdev') + 1]
        self.assertIn('hostfwd=tcp:127.0.0.1:22220-:22', net)
        for port in vm.WEB_PORTS:
            self.assertIn(f'hostfwd=tcp:127.0.0.1:{port}-:{port}', net)
        self.assertNotIn('18080', net)
        self.assertNotIn('19381', net)
        self.assertIn('Restart=on-failure', vm.unit_text(config))

    def test_rpm_kvm_fallback_must_emulate_x86(self):
        with patch.object(vm.shutil, 'which', return_value=None), patch.object(Path, 'is_file', return_value=True), \
                patch.object(vm.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'virt ARM Virtual Machine\n')):
            self.assertIsNone(vm.qemu_binary())
        with patch.object(vm.shutil, 'which', return_value=None), patch.object(Path, 'is_file', return_value=True), \
                patch.object(vm.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'pc-q35-8.2 Standard PC\n')):
            self.assertEqual(vm.qemu_binary(), '/usr/libexec/qemu-kvm')

    def test_repeated_bootstrap_does_not_install_or_download_host_packages(self):
        with patch.object(vm.platform, 'system', return_value='Linux'), patch.object(vm.os, 'geteuid', return_value=0), \
                patch.object(vm, 'missing_tools', return_value=[]), patch.object(vm, 'check'), \
                patch.object(vm, 'create'), patch.object(vm, 'wait_ready'), patch.object(vm, 'bootstrap') as install:
            vm.main(['--state-dir', str(self.root / 'vm'), '--bootstrap', 'start'])
        install.assert_not_called()

    def test_public_firewall_restricts_only_vm_ports_and_destination(self):
        options = self.options('--bind-address', '192.168.45.101', '--lan-cidr', '192.168.45.0/24', 'start')
        config = vm.settings(options)
        with patch.object(vm.shutil, 'which', return_value='/usr/sbin/iptables'), \
                patch.object(vm.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '')), \
                patch.object(vm, 'run') as write:
            vm.firewall(config)
        calls = [c.args for c in write.call_args_list]
        self.assertTrue(any('-s' in c and '192.168.45.0/24' in c and 'ACCEPT' in c for c in calls))
        self.assertTrue(any('DROP' in c for c in calls))
        jump = calls[-1]
        self.assertIn('INPUT', jump)
        self.assertIn('192.168.45.101/32', jump)
        self.assertIn(','.join(map(str, vm.WEB_PORTS)), jump)
        self.assertFalse(any('-F' in c or '-P' in c for c in calls))
        self.assertIn('ExecStartPre=', vm.unit_text(config))
        self.assertIn('helper.py', vm.unit_text(config))

    def test_loopback_vm_does_not_modify_host_firewall(self):
        with patch.object(vm.subprocess, 'run') as command, patch.object(vm, 'run') as write:
            vm.firewall(vm.settings(self.options('start')))
        command.assert_not_called()
        write.assert_not_called()

    def test_foreign_existing_firewall_chain_is_not_flushed(self):
        config = vm.settings(self.options('--bind-address', '192.168.45.101', 'start'))
        with patch.object(vm.shutil, 'which', return_value='/usr/sbin/iptables'), \
                patch.object(vm.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '-A strange -j ACCEPT\n')), \
                patch.object(vm, 'run') as write:
            with self.assertRaisesRegex(RuntimeError, 'without flushing'):
                vm.firewall(config)
        write.assert_not_called()

    def test_partial_disk_is_retained_without_running_commands(self):
        options = self.options('start')
        options.state_dir.mkdir()
        disk = options.state_dir / 'guest.qcow2'
        disk.write_bytes(b'valuable-existing-disk')
        with patch.object(vm, 'run', side_effect=AssertionError('must not mutate')):
            with self.assertRaisesRegex(RuntimeError, 'Partial VM'):
                vm.create(options)
        self.assertEqual(disk.read_bytes(), b'valuable-existing-disk')

    def test_existing_vm_reuses_disk_identity_and_unit(self):
        options = self.options('start')
        options.state_dir.mkdir()
        config = vm.settings(options)
        options.state_dir.joinpath('vm.json').write_text(json.dumps(config))
        for name in ('guest.qcow2', 'seed.img', 'id_ed25519', 'id_ed25519.pub'):
            options.state_dir.joinpath(name).write_bytes(name.encode())
        unit = self.root / 'unit'
        unit.write_text(vm.unit_text(config))
        with patch.object(vm, 'UNIT', unit), patch.object(vm, 'run') as call, \
                patch.object(vm, 'image', side_effect=AssertionError('must not download')):
            vm.create(options)
        call.assert_called_once_with('systemctl', 'enable', '--now', vm.SERVICE)
        self.assertEqual(options.state_dir.joinpath('guest.qcow2').read_bytes(), b'guest.qcow2')
        options.bind_address = '192.0.2.1'
        with self.assertRaisesRegex(RuntimeError, 'settings differ'):
            vm.create(options)

    def test_default_proxy_actions_reuse_deployed_public_vm_settings(self):
        original = self.options('--bind-address', '192.168.45.101', '--lan-cidr', '192.168.45.0/24',
                                '--memory-mib', '12288', '--cpus', '3', '--ssh-port', '22230', 'start')
        original.state_dir.mkdir()
        config = vm.settings(original)
        original.state_dir.joinpath('vm.json').write_text(json.dumps(config))
        for action in ('run', 'package'):
            with self.subTest(action=action), patch.object(vm.platform, 'system', return_value='Linux'), \
                    patch.object(vm.os, 'geteuid', return_value=0), patch.object(vm, 'check'), \
                    patch.object(vm, 'create') as create, patch.object(vm, 'wait_ready'), patch.object(vm, 'proxy') as proxy:
                vm.main(['--state-dir', str(original.state_dir), '--bind-address', '127.0.0.1',
                         '--lan-cidr', '127.0.0.0/8', action])
                self.assertEqual(vm.settings(create.call_args.args[0]), config)
                self.assertIn('PPCI_PUBLIC_HOST=192.168.45.101', vm.guest_command(proxy.call_args.args[0]))
        options = self.options('status')
        vm.reuse_settings(options)
        self.assertEqual(options.ssh_port, 22230)

    def test_proxy_action_does_not_create_an_unrequested_new_vm(self):
        with self.assertRaisesRegex(RuntimeError, 'initial deployment'):
            vm.reuse_settings(self.options('run'))

    def test_status_uses_guest_private_gateway_and_saved_public_origin(self):
        options = self.options('--bind-address', '192.168.45.101', '--lan-cidr', '192.168.45.0/24', 'start')
        options.state_dir.mkdir()
        options.state_dir.joinpath('vm.json').write_text(json.dumps(vm.settings(options)))
        unit = self.root / 'unit'
        unit.write_text(vm.MARKER)
        with patch.object(vm, 'UNIT', unit), patch.object(vm.platform, 'system', return_value='Linux'), \
                patch.object(vm.os, 'geteuid', return_value=0), patch.object(vm, 'run'), patch.object(vm, 'remote') as remote:
            vm.main(['--state-dir', str(options.state_dir), 'status'])
        args = remote.call_args.args[1]
        self.assertIn('10.0.2.15', args)
        self.assertIn('PPCI_PUBLIC_HOST=192.168.45.101', args)

    def test_source_archive_accepts_internal_links(self):
        path = self.archive([('ppci-source/include/header.h', 'sym', '../actual.h'),
                             ('ppci-source/header2.h', 'hard', 'ppci-source/actual.h'),
                             ('ppci-source/actual.h', 'file', '')])
        vm.validate_source(path)

    def test_source_archive_rejects_escape_cycles_and_link_children(self):
        attacks = [
            [('ppci-source/../../escape', 'file', '')],
            [('ppci-source/link', 'sym', '/etc/passwd')],
            [('ppci-source/link', 'sym', '../../etc/passwd')],
            [('ppci-source/a', 'sym', 'b'), ('ppci-source/b', 'sym', 'a')],
            [('ppci-source/link', 'sym', 'dir'), ('ppci-source/link/file', 'file', '')],
        ]
        for items in attacks:
            with self.subTest(items=items), self.assertRaises(RuntimeError):
                vm.validate_source(self.archive(items))

    def test_guest_action_uses_private_guest_address_and_prevents_override(self):
        options = self.options('deploy', 'all', '--no-tests')
        args = vm.guest_command(options)
        self.assertIn('all', args)
        self.assertEqual(args[-1], '--no-tests')
        self.assertIn('10.0.2.15', args)
        self.assertIn('10.0.2.0/24', args)
        self.assertIn('PPCI_PUBLIC_HOST=127.0.0.1', args)
        with self.assertRaisesRegex(RuntimeError, 'managed'):
            vm.guest_command(self.options('deploy', 'all', '--host', '1.2.3.4'))

    def test_package_copies_guest_release_to_host(self):
        output = self.root / 'release'
        options = self.options('package', '--output', str(output), '--with-images')
        with patch.object(vm, 'remote') as remote, patch.object(vm, 'run') as call:
            vm.proxy(options)
        guest = remote.call_args_list[0].args[1]
        self.assertIn('--with-images', guest)
        self.assertNotIn(str(output), guest)
        self.assertIn('ppci@127.0.0.1:/home/ppci/export-', call.call_args.args[-2])
        self.assertEqual(call.call_args.args[-1], str(output.resolve()) + '/')

    def test_package_default_output_is_a_new_host_dist_directory(self):
        with patch.object(Path, 'cwd', return_value=self.root), patch.object(vm.time, 'strftime', return_value='test-release'), \
                patch.object(vm, 'remote'), patch.object(vm, 'run') as call:
            vm.proxy(self.options('package', '--with-images'))
        self.assertEqual(call.call_args.args[-1], str((self.root / 'dist/test-release').resolve()) + '/')

    def test_package_never_overwrites_existing_host_export(self):
        output = self.root / 'release'
        output.mkdir()
        valuable = output / 'images.tar.gz'
        valuable.write_bytes(b'original')
        with patch.object(vm, 'remote') as remote, patch.object(vm, 'run') as call:
            with self.assertRaises(FileExistsError):
                vm.proxy(self.options('package', '--output', str(output)))
        remote.assert_not_called()
        call.assert_not_called()
        self.assertEqual(valuable.read_bytes(), b'original')

    def test_missing_offline_directory_prevents_guest_execution(self):
        options = self.options('deploy', 'all', '--offline', str(self.root / 'missing'))
        with patch.object(vm, 'remote') as remote:
            with self.assertRaisesRegex(RuntimeError, 'existing host bundle'):
                vm.proxy(options)
        remote.assert_not_called()

    def test_readiness_is_bounded_and_keeps_guest(self):
        options = self.options('start')
        with patch.object(vm.time, 'monotonic', side_effect=[0, options.wait_seconds + 1]), \
                patch.object(vm, 'run') as call:
            with self.assertRaisesRegex(TimeoutError, 'retained'):
                vm.wait_ready(options)
        call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
