import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_patch', ROOT / 'apply-source-patch.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class SourcePatchTests(unittest.TestCase):
    def test_apply_reverse_and_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            checkout = Path(folder) / 'checkout'
            shutil.copytree(ROOT / 'patches/original', checkout)
            count = len(json.loads((ROOT / 'patches/source-hashes.json').read_text()))
            self.assertEqual(p.apply(checkout), count)
            self.assertEqual(p.apply(checkout), 0)
            hashes = json.loads((ROOT / 'patches/source-hashes.json').read_text())
            for relative, record in hashes.items():
                self.assertEqual(p.sha((checkout / relative).read_bytes()), record['patched'])
            self.assertEqual(p.apply(checkout, reverse=True), count)
            self.assertEqual(p.apply(checkout, reverse=True), 0)
            self.assertFalse((checkout / 'dnscrypt-proxy/nextdns_device_names.go').exists())

    def test_mismatch_aborts_before_any_source_change(self):
        with tempfile.TemporaryDirectory() as folder:
            checkout = Path(folder) / 'checkout'
            shutil.copytree(ROOT / 'patches/original', checkout)
            target = checkout / 'dnscrypt-proxy/xtransport.go'
            target.write_bytes(target.read_bytes() + b'\n// unknown source change\n')
            before = {str(file.relative_to(checkout)): file.read_bytes() for file in checkout.rglob('*') if file.is_file()}
            with self.assertRaises(RuntimeError):
                p.apply(checkout)
            after = {str(file.relative_to(checkout)): file.read_bytes() for file in checkout.rglob('*') if file.is_file()}
            self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main(verbosity=2)
