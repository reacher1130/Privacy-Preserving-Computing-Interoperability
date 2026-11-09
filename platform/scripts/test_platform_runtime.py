import copy
import unittest

from platform_runtime import only_storage_blocks_tasks


class StorageReadinessTests(unittest.TestCase):
    def setUp(self):
        self.status = {
            'requesterConfigured': True, 'modelStorageType': 'XuperDB',
            'storageReady': False, 'executors': [{'ready': True}, {'ready': True}],
            'storage': [{'checked': True, 'ready': False}, {'checked': True, 'ready': False}],
        }

    def test_completed_red_probe_is_a_task_gate(self):
        self.assertTrue(only_storage_blocks_tasks(self.status))

    def test_incomplete_probe_or_broken_executor_remains_runtime_failure(self):
        for group, key in [('storage', 'checked'), ('executors', 'ready')]:
            status = copy.deepcopy(self.status)
            status[group][0][key] = False
            self.assertFalse(only_storage_blocks_tasks(status))
        self.status['storage'] = []
        self.assertFalse(only_storage_blocks_tasks(self.status))

    def test_unknown_storage_or_missing_requester_cannot_be_excused(self):
        self.status['modelStorageType'] = 'Unknown'
        self.assertFalse(only_storage_blocks_tasks(self.status))
        self.status['modelStorageType'] = 'XuperDB'
        self.status['requesterConfigured'] = False
        self.assertFalse(only_storage_blocks_tasks(self.status))


if __name__ == '__main__':
    unittest.main()
