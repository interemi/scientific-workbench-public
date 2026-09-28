#!/usr/bin/env python3
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def write_pid(pid_dir: Path, role: str) -> None:
    (pid_dir / f"{role}.pid").write_text(str(os.getpid()), encoding="utf-8")


def configure_signals(ignore_soft_signals: bool) -> None:
    if ignore_soft_signals:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)


def main() -> None:
    pid_dir = Path(sys.argv[1])
    role = sys.argv[2]
    ignore_soft_signals = sys.argv[3] == "ignore-soft"
    pid_dir.mkdir(parents=True, exist_ok=True)
    configure_signals(ignore_soft_signals)
    write_pid(pid_dir, role)

    if role == "grandchild":
        while True:
            time.sleep(1)

    next_role = "child" if role == "parent" else "grandchild"
    child = subprocess.Popen(
        [sys.executable, __file__, str(pid_dir), next_role, sys.argv[3]]
    )
    child.wait()


if __name__ == "__main__":
    main()
