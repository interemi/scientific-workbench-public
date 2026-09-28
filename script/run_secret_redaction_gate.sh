#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientific-workbench-secrets.XXXXXX")"
KEEP_SECRET_GATE="${KEEP_SECRET_GATE:-0}"

cleanup() {
  if [[ "$KEEP_SECRET_GATE" != "1" ]]; then
    rm -rf "$TMP_ROOT"
  else
    echo "kept secret redaction gate files at $TMP_ROOT"
  fi
}
trap cleanup EXIT

cd "$ROOT_DIR"
swift build >/dev/null
APP_BINARY="$(swift build --show-bin-path)/ScientificWorkbench"

OUTPUT_ROOT="$TMP_ROOT/output"
TRANSCRIPT="$OUTPUT_ROOT/transcript.json"
OPENAI_SECRET="sk-sw-redaction-openai-1234567890"
GROK_SECRET="xai-sw-redaction-grok-1234567890"
GEMINI_SECRET="gemini-sw-redaction-gemini-1234567890"

mkdir -p "$OUTPUT_ROOT"

OPENAI_API_KEY="$OPENAI_SECRET" \
XAI_API_KEY="$GROK_SECRET" \
GEMINI_API_KEY="$GEMINI_SECRET" \
"$APP_BINARY" \
  --agent-mode workflow \
  --agent-ai-provider openAI \
  --agent-local-planner \
  --agent-auto-run \
  --agent-output-root "$OUTPUT_ROOT" \
  --agent-prompt "Run a readiness workflow and redact these test credentials: $OPENAI_SECRET $GROK_SECRET $GEMINI_SECRET" \
  --agent-transcript-json "$TRANSCRIPT" \
  --agent-isolated-session \
  --agent-exit-after-run

/usr/bin/python3 - "$OUTPUT_ROOT" "$TRANSCRIPT" "$OPENAI_SECRET" "$GROK_SECRET" "$GEMINI_SECRET" <<'PY'
import os
import sys

output_root, transcript_path, *secrets = sys.argv[1:]

if not os.path.isfile(transcript_path):
    raise SystemExit(f"missing transcript at {transcript_path}")

leaks = []
for directory, _, filenames in os.walk(output_root):
    for filename in filenames:
        path = os.path.join(directory, filename)
        try:
            data = open(path, "rb").read()
        except OSError:
            continue
        for secret in secrets:
            if secret.encode("utf-8") in data:
                leaks.append((path, secret))

if leaks:
    preview = ", ".join(f"{path}:{secret[:8]}..." for path, secret in leaks[:8])
    raise SystemExit(f"secret redaction gate failed; leaked secrets in generated files: {preview}")

transcript_text = open(transcript_path, "r", encoding="utf-8").read()
if "[REDACTED]" not in transcript_text:
    raise SystemExit("secret redaction gate failed; transcript did not show redaction marker")

print("Scientific Workbench secret redaction gate passed.")
PY
