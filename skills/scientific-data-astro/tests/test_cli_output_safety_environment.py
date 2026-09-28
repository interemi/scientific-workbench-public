"""Focused regression tests split from a larger safety module."""

from __future__ import annotations

from astro_cli_output_safety_support import *  # noqa: F403


class AstroCliOutputSafetyRegressionTest(AstroCliCollisionAssertions, unittest.TestCase):
    def test_environment_executables_with_spaces_are_protected(self) -> None:
        for variable in ("STILTS_COMMAND", "TOPCAT_COMMAND", "JAVA_COMMAND", "APT_COMMAND"):
            for alias_kind in ("exact", "hardlink"):
                with self.subTest(variable=variable, alias=alias_kind), tempfile.TemporaryDirectory() as raw:
                    root = Path(raw)
                    binary_dir = root / "backend with spaces"
                    binary_dir.mkdir()
                    command = binary_dir / "synthetic tool"
                    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    command.chmod(0o700)
                    output = command
                    if alias_kind == "hardlink":
                        output = root / "summary.json"
                        os.link(command, output)
                    table = root / "table.csv"
                    table.write_text("x,y\n1,2\n", encoding="utf-8")
                    before_mode = command.stat().st_mode
                    self.assert_controlled_collision(
                        root,
                        "stilts_workbench.py",
                        ["convert", str(table), str(root / "converted.csv"), "--summary-json", str(output)],
                        {variable: str(command)},
                    )
                    self.assertEqual(command.stat().st_mode, before_mode)

    def test_environment_and_implicit_secret_inputs_are_protected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            table = root / "table.csv"
            table.write_text("x,y\n1,2\n", encoding="utf-8")
            command = root / "stilts-command"
            command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            command.chmod(0o700)
            before_mode = command.stat().st_mode
            self.assert_controlled_collision(
                root,
                "stilts_workbench.py",
                [
                    "convert",
                    str(table),
                    str(root / "converted.csv"),
                    "--summary-json",
                    str(command),
                ],
                {"STILTS_COMMAND": str(command)},
            )
            self.assertEqual(command.stat().st_mode, before_mode)

            bin_dir = root / "bin"
            bin_dir.mkdir()
            apt_command = bin_dir / "APT.csh"
            apt_command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            apt_command.chmod(0o700)
            before_mode = apt_command.stat().st_mode
            self.assert_controlled_collision(
                root,
                "apt_workbench.py",
                ["preflight", "--summary-json", str(apt_command)],
                {"PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")},
            )
            self.assertEqual(apt_command.stat().st_mode, before_mode)

            key_file = root / "astrometry.key"
            key_file.write_text("synthetic-secret\n", encoding="utf-8")
            self.assert_controlled_collision(
                root,
                "astrometry_net_workbench.py",
                [
                    "auth-check",
                    "--api-base",
                    "http://127.0.0.1:9",
                    "--summary-json",
                    str(key_file),
                ],
                {
                    "ASTROMETRY_NET_API_KEY": "",
                    "ASTROMETRY_NET_API_KEY_FILE": str(key_file),
                },
            )


if __name__ == "__main__":
    unittest.main()
