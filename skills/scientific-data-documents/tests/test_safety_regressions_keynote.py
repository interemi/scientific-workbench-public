"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from document_safety_support import *  # noqa: F403


class DocumentSafetyRegressionTest(unittest.TestCase):
    def test_keynote_auxiliary_collisions_preserve_deck_in_preflight(self) -> None:
        for flag in ("--log-txt", "--summary-json", "--manifest-json"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                deck = root / "copied-deck.pptx"
                deck.write_bytes(b"copied presentation")
                before = sha256(deck)
                pdf = root / "derived.pdf"

                completed = run_script(
                    "keynote_export.py",
                    deck,
                    pdf,
                    "--preflight-only",
                    flag,
                    deck,
                )

                self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
                self.assertEqual(completed.stderr, "")
                self.assertEqual(sha256(deck), before)
                self.assertFalse(pdf.exists())
                payload = strict_json(completed.stdout)
                self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
                self.assertEqual(payload["results"]["collisions"][0]["flag"], flag)

    def test_keynote_collision_block_precedes_capability_and_early_error_paths(self) -> None:
        collision_cases = (
            ("pdf_path", None),
            ("--log-txt", "--log-txt"),
            ("--summary-json", "--summary-json"),
            ("--manifest-json", "--manifest-json"),
        )
        for expected_flag, option in collision_cases:
            with self.subTest(flag=expected_flag), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                deck = root / "copied-deck.pptx"
                deck.write_bytes(b"copied presentation")
                before = sha256(deck)
                pdf = deck if option is None else root / "derived.pdf"
                argv = ["keynote_export.py", str(deck), str(pdf)]
                if option:
                    argv.extend([option, str(deck)])
                stdout = io.StringIO()
                stderr = io.StringIO()

                with (
                    patch.object(sys, "argv", argv),
                    patch.object(
                        keynote_export,
                        "build_capability_report",
                        side_effect=AssertionError("capability probe must not run for a deck collision"),
                    ),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                    self.assertRaises(SystemExit) as raised,
                ):
                    keynote_export.main()

                self.assertEqual(raised.exception.code, 2)
                self.assertEqual(stderr.getvalue(), "")
                self.assertEqual(sha256(deck), before)
                if pdf != deck:
                    self.assertFalse(pdf.exists())
                payload = strict_json(stdout.getvalue())
                self.assertEqual(payload["app_status"], "BLOCKED_CONTROLADO")
                self.assertEqual(payload["results"]["collisions"][0]["flag"], expected_flag)

    def test_keynote_auxiliary_inside_key_package_is_blocked_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            deck = root / "copied.key"
            deck.mkdir()
            (deck / "index.apxl").write_bytes(b"keynote package")
            before = directory_snapshot(deck)
            summary = deck / "derived" / "summary.json"
            pdf = root / "derived.pdf"

            completed = run_script(
                "keynote_export.py",
                deck,
                pdf,
                "--preflight-only",
                "--summary-json",
                summary,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr or completed.stdout)
            self.assertEqual(completed.stderr, "")
            self.assertEqual(directory_snapshot(deck), before)
            self.assertFalse(summary.exists())
            self.assertFalse(pdf.exists())
            self.assertEqual(strict_json(completed.stdout)["app_status"], "BLOCKED_CONTROLADO")


if __name__ == "__main__":
    unittest.main()
