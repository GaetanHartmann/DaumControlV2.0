"""Network-free checks for corrupted references and cache replacement."""
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from download_daum_material import MAX_BYTES, download, reference


class Response(io.BytesIO):
    headers = {'Content-Type': 'application/octet-stream'}

    def geturl(self):
        return 'https://raw.githubusercontent.com/author/project/pinned/ref.pdf'


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.target = Path(self.directory.name)
        self.item = reference('ref.pdf', 'author/project', 'pinned', 'ref.pdf', 'local only')
        (self.target / 'ref.pdf').write_bytes(b'previous reference')

    def test_html_error_page_cannot_replace_document(self):
        with self.assertRaisesRegex(ValueError, 'Expected PDF'):
            download(self.item, self.target, opener=lambda *a, **k: Response(b'<html>error</html>'))
        self.assertEqual((self.target / 'ref.pdf').read_bytes(), b'previous reference')

    def test_checksum_mismatch_preserves_previous_copy(self):
        self.item['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'checksum'):
            download(self.item, self.target, opener=lambda *a, **k: Response(b'%PDF-new'))
        self.assertEqual((self.target / 'ref.pdf').read_bytes(), b'previous reference')
        self.assertFalse((self.target / 'ref.pdf.part').exists())

    def test_size_limit_prevents_replacement(self):
        with self.assertRaisesRegex(ValueError, 'size limit'):
            download(self.item, self.target,
                     opener=lambda *a, **k: Response(b'%PDF-' + b'x' * MAX_BYTES))
        self.assertEqual((self.target / 'ref.pdf').read_bytes(), b'previous reference')

    def test_valid_document_has_provenance_and_complete_checksum(self):
        content = b'%PDF-1.4\nreference bytes'
        self.item['sha256'] = hashlib.sha256(content).hexdigest()
        record = download(self.item, self.target, opener=lambda *a, **k: Response(content))
        self.assertEqual((self.target / 'ref.pdf').read_bytes(), content)
        self.assertEqual(record['sha256'], self.item['sha256'])
        self.assertEqual(record['bytes'], len(content))
        self.assertEqual(record['license_state'], 'local only')
        self.assertTrue(record['downloaded_at'])

    def test_reference_cannot_escape_cache(self):
        self.item['name'] = '../ref.pdf'
        with self.assertRaisesRegex(ValueError, 'filename'):
            download(self.item, self.target, opener=lambda *a, **k: self.fail('Network not expected'))


if __name__ == '__main__':
    unittest.main()
