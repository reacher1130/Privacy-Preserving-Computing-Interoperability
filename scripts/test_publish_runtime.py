import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publish_runtime', Path(__file__).with_name('publish-runtime.py'))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublisherTests(unittest.TestCase):
    def test_unreviewed_release_identity_stops_before_staging_or_authentication(self):
        for tag, checksum in (('../another-directory', 'a' * 64),
                              ('runtime-20261109-abcdef0', 'unreviewed')):
            with self.subTest(tag=tag), patch.dict(os.environ, {'RELEASE_TAG': tag, 'INPUT_SHA256': checksum}, clear=True), \
                 patch.object(publisher, 'digest') as digest, self.assertRaises(ValueError):
                publisher.main()
            digest.assert_not_called()

    def test_release_upload_streams_file_instead_of_buffering_it(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / 'artifact.tar.gz'
            artifact.write_bytes(b'abcdef')

            def upload(request, timeout):
                self.assertEqual(request.get_header('Content-length'), '6')
                self.assertTrue(hasattr(request.data, 'read'))
                self.assertEqual(request.data.read(3), b'abc')
                self.assertEqual(request.data.read(3), b'def')
                return io.BytesIO(b'{"id":1}')

            with patch.object(publisher.urllib.request, 'urlopen', side_effect=upload):
                self.assertEqual(publisher.api('https://uploads.github.com/repos/owner/repo/releases/1/assets?name=x',
                                               'test-token', upload=artifact), {'id': 1})


if __name__ == '__main__':
    unittest.main()
