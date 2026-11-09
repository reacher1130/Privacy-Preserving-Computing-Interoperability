import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None


ENVIRONMENTS = Path(__file__).resolve().parents[1] / 'platform/scripts/environments'
sys.path.insert(0, str(ENVIRONMENTS))
spec = importlib.util.spec_from_file_location('paddle_provision', ENVIRONMENTS / 'paddle-provision.py')
paddle = importlib.util.module_from_spec(spec)
# prepare() does not parse YAML; keep this configuration check dependency-free.
with patch.dict(sys.modules, {'yaml': ModuleType('yaml')}):
    spec.loader.exec_module(paddle)


class PaddleProvisionTests(unittest.TestCase):
    @unittest.skipUnless(tomllib is not None, 'Semantic TOML validation requires Python 3.11+')
    def test_native_executor_and_requester_contract_fields_preserve_existing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / 'PaddleDTX/testdatatmp'
            mnemonic = work / 'blockchain/xchain/user/mnemonic'
            mnemonic.parent.mkdir(parents=True)
            mnemonic.write_text('public demo fixture')
            originals = {}
            for node in range(1, 4):
                conf = work / f'executor/node{node}/conf'
                conf.mkdir(parents=True)
                keys = conf.parent / 'keys'
                keys.mkdir()
                (keys / 'private.key').write_text('unchanged test fixture; never parsed as a key')
                text = ('[executor]\nname = "executor' + str(node) + '"\nkeyPath = "./keys"\n'
                        '[executor.blockchain.xchain]\nmnemonic = "retained identity"\n'
                        'contractName = "custom-contract"\ncontractAccount = "retained account"\n'
                        'chainAddress = "retained-host:37101"\nchainName = "retained-chain"\n'
                        '[executor.blockchain.fabric]\ncontractName = "other-section"\n'
                        '[executor.storage]\nlocalModelStoragePath = "./models"\n'
                        'localEvaluationStoragePath = "./evalus"\ntype = "Local"\n'
                        '[executor.storage.XuperDB]\nhost = "retained-storage-host"\nkeyPath = "./ukeys"\n'
                        '[executor.storage.Local]\nlocalPredictStoragePath = "./predictions"\n')
                if node == 3:
                    text = text.replace('contractName = "custom-contract"',
                                        'contractName = "custom-contract"\ndtxContractName = "native-custom"\nmanagerContractName = "manager-custom"')
                    text = text.replace('localModelStoragePath = "./models"',
                                        'localModelStoragePath = "./models"\nmodelStorageType = "Local"\n'
                                        'predictStorageType = "Local"\npsiStorageType = "Local"\n'
                                        'localPredictStoragePath = "./custom-predictions"\n'
                                        'localPsiStoragePath = "./custom-psi"\nliveEvaluationStoragePath = "./custom-live"')
                    original_xdb = conf.parent / 'ukeys'
                    original_xdb.mkdir()
                    (original_xdb / 'private.key').write_text('existing configured identity; never parsed')
                for name in ('config.toml', 'requester-config.toml') if node != 2 else ('config.toml',):
                    path = conf / name
                    content = text
                    if node == 1 and name == 'requester-config.toml':
                        content = content.replace('[executor.storage]\n', '[executor.storage]\nmodelStorageType = "XuperDB"\n')
                    path.write_text(content)
                    path.chmod(0o600)
                    originals[path] = tomllib.loads(content)
            network = subprocess.CompletedProcess([], 0, stdout=json.dumps([{'IPAM': {'Config': [{'Subnet': '172.31.1.0/24'}]}}]))
            with patch.multiple(paddle, SOURCE=root / 'source', ROOT=root, WORK=work), \
                 patch.object(paddle, 'run'), patch.object(paddle.subprocess, 'run', return_value=network):
                paddle.prepare()
                first = {path: path.read_bytes() for path in work.glob('executor/node*/conf/*.toml')}
                paddle.prepare()
            self.assertEqual(len(first), 6)
            for path, content in first.items():
                self.assertEqual(path.read_bytes(), content)
                parsed = tomllib.loads(content.decode())
                chain = parsed['executor']['blockchain']['xchain']
                native = 'node3' in path.parts
                self.assertEqual(chain['dtxContractName'], 'native-custom' if native else 'custom-contract')
                self.assertEqual(chain['managerContractName'], 'manager-custom' if native else 'data')
                old = originals.get(path, originals[path.with_name('config.toml')])
                for key, value in old['executor']['blockchain']['xchain'].items():
                    self.assertEqual(chain[key], value)
                self.assertEqual(parsed['executor']['blockchain']['fabric'], old['executor']['blockchain']['fabric'])
                storage = parsed['executor']['storage']
                for key in ('modelStorageType', 'predictStorageType', 'psiStorageType'):
                    self.assertEqual(storage[key], old['executor']['storage'].get(key, 'Local'))
                self.assertEqual(storage['localPredictStoragePath'], './custom-predictions' if native else './predictions')
                self.assertEqual(storage['localPsiStoragePath'], './custom-psi' if native else './predictions/psi')
                self.assertEqual(storage['liveEvaluationStoragePath'], './custom-live' if native else './evalus/live')
                for key, value in old['executor']['storage'].items():
                    if key == 'XuperDB':
                        retain_xdb = native or storage['modelStorageType'] == 'XuperDB'
                        value = dict(value, keyPath='./ukeys' if retain_xdb else './keys')
                    self.assertEqual(storage[key], value)
                self.assertEqual((path.parent.parent / 'keys/private.key').read_text(),
                                 'unchanged test fixture; never parsed as a key')
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
