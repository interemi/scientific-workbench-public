import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "script"))
from check_scientific_known_answers import check_manifest


class ScientificExampleEvidenceTests(unittest.TestCase):
    def test_hash_match_cannot_hide_a_wrong_manifest_path_or_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            artifact = root / "synthetic.csv"
            artifact.write_bytes(b"flux\n1.2\n")
            record = {
                "path": str(artifact),
                "exists": True,
                "size_bytes": artifact.stat().st_size,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
            manifest = root / "manifest.json"

            def write(output):
                manifest.write_text(json.dumps({"inputs": [], "outputs": [output]}), encoding="utf-8")

            write(record)
            check_manifest(manifest, [], [artifact])
            write({**record, "path": str(root / "different.csv")})
            with self.assertRaisesRegex(ValueError, "manifest output path differs"):
                check_manifest(manifest, [], [artifact])
            write({**record, "size_bytes": 1})
            with self.assertRaisesRegex(ValueError, "manifest output size differs"):
                check_manifest(manifest, [], [artifact])
            self.assertEqual(artifact.read_bytes(), b"flux\n1.2\n")
