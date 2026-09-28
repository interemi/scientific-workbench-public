# Deployment Quickstart

Use this when you want the shortest realistic path to move the skill to another machine.

## 1. Copy The Skill

Place the folder here:

```text
~/.codex/skills/scientific-data-analysis
```

## 2. Choose An Install Route

### macOS or Linux

Core only:

```bash
bash deploy/install-core.sh
```

Broader stack:

```bash
bash deploy/install-full.sh
```

Conda:

```bash
bash deploy/install-conda.sh
```

### Windows PowerShell

Core only:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\install-core.ps1
```

Broader stack:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\install-full.ps1
```

Conda:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\install-conda.ps1
```

## 3. Run The Portable Smoke Test

The wrapper prefers the local `.venv` interpreter when it exists. If you are using a different Python, set `PYTHON_BIN` first.

### macOS or Linux

```bash
bash deploy/run-smoke-test.sh
```

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\run-smoke-test.ps1
```

## 4. Read The Result

Check:

- `deploy/smoke-test-output/summary.json`
- `deploy/smoke-test-output/manifest.json`
- `deploy/env_doctor.*.json`

If the smoke test passes, the machine is ready for normal use of the stable core.

## Notes

- The smoke test uses packaged examples and generated files, not user data.
- The generated summaries and manifests should avoid exposing machine-specific absolute home paths and hostnames.
- Optional tools such as LibreOffice, LaTeX, Quick Look, Keynote, and TEAREDUCE are still optional.
- For deeper portability details, read `portable-install.md`.
