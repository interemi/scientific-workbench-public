"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from document_safety_support import *  # noqa: F403


class DocumentSafetyRegressionTest(unittest.TestCase):
    def test_semantic_diff_output_input_collisions_are_stdout_only(self) -> None:
        for flag in ("--output-json", "--summary-json", "--output-md", "--manifest-json"):
            for input_name in ("baseline", "candidate"):
                with self.subTest(flag=flag, input_name=input_name), tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    baseline = root / "baseline.csv"
                    candidate = root / "candidate.csv"
                    baseline.write_text("id,value\n1,old\n", encoding="utf-8")
                    candidate.write_text("id,value\n1,new\n", encoding="utf-8")
                    before = {"baseline": sha256(baseline), "candidate": sha256(candidate)}
                    colliding_path = baseline if input_name == "baseline" else candidate

                    completed = run_script(
                        "semantic_diff.py",
                        baseline,
                        candidate,
                        flag,
                        colliding_path,
                    )

                    self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                    self.assertEqual(completed.stderr, "")
                    self.assertEqual(sha256(baseline), before["baseline"])
                    self.assertEqual(sha256(candidate), before["candidate"])
                    payload = strict_json(completed.stdout)
                    self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
                    self.assertEqual(payload["results"]["collisions"][0]["flag"], flag)
                    self.assertEqual(payload["results"]["collisions"][0]["input"], input_name)

    def test_semantic_diff_rejects_output_output_aliases_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            baseline = root / "baseline.csv"
            candidate = root / "candidate.csv"
            baseline.write_text("id,value\n1,old\n", encoding="utf-8")
            candidate.write_text("id,value\n1,new\n", encoding="utf-8")
            shared_output = root / "shared.json"
            before = {"baseline": sha256(baseline), "candidate": sha256(candidate)}

            completed = run_script(
                "semantic_diff.py",
                baseline,
                candidate,
                "--summary-json",
                shared_output,
                "--manifest-json",
                shared_output,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            self.assertFalse(shared_output.exists())
            self.assertEqual(
                {"baseline": sha256(baseline), "candidate": sha256(candidate)},
                before,
            )
            payload = strict_json(completed.stdout)
            self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
            self.assertEqual(
                payload["results"]["collisions"][0]["collision_kind"],
                "output_output_alias",
            )

    def test_txt_routes_as_document(self) -> None:
        self.assertFalse(semantic_diff.table_like(Path("notes.txt")))
        self.assertTrue(semantic_diff.table_like(Path("table.csv")))

    def test_failure_bundle_always_has_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            layout = ensure_run_bundle(Path(raw) / "run")
            payload = {"app_status": "FAIL", "artifacts": {}, "qa": {"status": "fail"}}
            finalize_existing_run_bundle(layout, payload, returncode=2)
            self.assertTrue(layout.manifest_json.is_file())
            json.loads(layout.manifest_json.read_text(encoding="utf-8"))

    def test_package_collision_is_controlled_and_preserves_existing_zip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "report.md"
            source.write_text("report", encoding="utf-8")
            package = root / "handoff.zip"
            package.write_bytes(b"existing-package")
            before = sha256(package)
            completed = run_script("deliverable_factory.py", "package", package, source)
            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(sha256(package), before)
            self.assertIn("BLOCKED_CONTROLADO", completed.stdout)

    def test_package_inside_input_directory_is_blocked_before_any_writes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "report.md").write_text("report", encoding="utf-8")
            before = directory_snapshot(source)
            package = source / "handoff.zip"

            completed = run_script("deliverable_factory.py", "package", package, source)

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(directory_snapshot(source), before)
            self.assertFalse(package.exists())
            self.assertFalse(package.with_suffix(".README.md").exists())
            self.assertFalse(package.with_suffix(".index.json").exists())
            self.assertEqual(strict_json(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")

    def test_package_manifest_inside_input_directory_is_blocked_before_any_writes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "report.md").write_text("report", encoding="utf-8")
            before = directory_snapshot(source)
            package = root / "handoff.zip"
            manifest = source / "manifest.json"

            completed = run_script(
                "deliverable_factory.py",
                "package",
                package,
                source,
                "--manifest-json",
                manifest,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(directory_snapshot(source), before)
            self.assertFalse(package.exists())
            self.assertFalse(package.with_suffix(".README.md").exists())
            self.assertFalse(package.with_suffix(".index.json").exists())
            self.assertFalse(manifest.exists())
            self.assertEqual(strict_json(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")


if __name__ == "__main__":
    unittest.main()
