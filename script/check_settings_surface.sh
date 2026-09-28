#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

/usr/bin/python3 - "$ROOT_DIR" <<'PY'
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
settings_surface_paths = [
    root / "Sources/ScientificWorkbench/Views/SettingsView.swift",
    root / "Sources/ScientificWorkbench/Views/CapabilityTimeoutControl.swift",
    root / "Sources/ScientificWorkbench/Views/OllamaSetupView.swift",
    root / "Sources/ScientificWorkbench/Views/ProviderConnectionRow.swift",
]
settings = "\n".join(
    path.read_text(encoding="utf-8")
    for path in settings_surface_paths
)
store = (root / "Sources/ScientificWorkbench/Stores/WorkbenchStore.swift").read_text(encoding="utf-8")
ollama_models = (root / "Sources/ScientificWorkbench/Models/OllamaSetupModels.swift").read_text(encoding="utf-8")
tests_root = root / "Tests/ScientificWorkbenchTests"
tests = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted(tests_root.glob("*.swift"))
)
all_text = "\n".join([settings, store, ollama_models, tests])

def fail(message: str) -> None:
    raise SystemExit(f"settings surface check failed: {message}")

required_settings_text = [
    'Section("Setup Checklist")',
    'Section("Paths")',
    'Section("Behavior")',
    'Section("Configuration")',
    'Section("Help And Output")',
    'Section("Local AI Setup")',
    'Section("AI Connections")',
    'Section("Codex Bridge")',
    'Section("Environment Details")',
    'TextField("Mother skill root"',
    'TextField("Output root"',
    'TextField("Python executable"',
    'CapabilityTimeoutControl(minutes: $store.externalProcessTimeoutMinutes)',
    'Text("Capability timeout (minutes)")',
    'Slider(',
    '.labelsHidden()',
    '.frame(maxWidth: .infinity)',
    '.accessibilityLabel("Capability timeout (minutes)")',
    'Button("Save Settings")',
    'Button("Reload Registry")',
    'Button("Refresh Environment")',
    'Button("Export Configuration")',
    'Button("Import Configuration")',
    'Button("Open User Guide")',
    'Button("Reveal Output Folder")',
    'Button("Export Support Bundle")',
    'Label("Ollama local AI"',
    'Picker("Model profile"',
    'TextField("Custom Ollama model"',
    'TextField("Local endpoint"',
    'Button("Install Ollama")',
    'Button("Open Ollama")',
    'Button(store.isCheckingOllamaSetup ? "Checking..." : "Check")',
    'Button(store.isPullingOllamaModel ? "Downloading..." : "Download Selected Model")',
    'Button("Test Local AI")',
    'Picker("Provider"',
    'Picker("Cloud attachment context"',
    'SecureField(credentialPlaceholder',
    'Button(status.state == .testing ? "Testing..." : "Test Connection")',
    'Button("Save Connections")',
    'TextField("Codex executable"',
    'Button("Save Codex Settings")',
]

missing = [needle for needle in required_settings_text if needle not in settings]
if missing:
    fail("missing Settings surface elements: " + ", ".join(missing))

if not re.search(
    r'Button\("Save Connections"\)\s*\{\s*store\.persistSettings\(saveSecrets:\s*true\)',
    settings,
):
    fail("Save Connections must explicitly persist edited credentials")

required_copy = [
    "API keys are never exported or imported.",
    "Maximum time for each capability process.",
    "No API key required. Uses a local Ollama server.",
    "OpenAI, Grok/xAI, and Gemini remain optional cloud providers",
    "After installation, open Ollama once, download the model here, then run Test Local AI.",
    "Ollama and the deterministic local planner are not affected.",
]
missing_copy = [needle for needle in required_copy if needle not in settings]
if missing_copy:
    fail("missing safety/setup copy: " + ", ".join(missing_copy))

if 'Text("Danger full access")' in settings:
    fail("Scientific Workbench must not expose unrestricted Codex filesystem access")

provider_placeholders = [
    "OpenAI API key",
    "Grok / xAI API key",
    "Gemini API key",
]
missing_placeholders = [needle for needle in provider_placeholders if needle not in settings]
if missing_placeholders:
    fail("missing cloud credential placeholders: " + ", ".join(missing_placeholders))

model_profiles = [
    'id: "compact"',
    'model: "qwen3:1.7b"',
    'id: "balanced"',
    'model: "qwen3:4b-instruct"',
    'id: "stronger"',
    'model: "qwen3:8b"',
    "static var recommended: OllamaModelProfile { .balanced }",
]
missing_models = [needle for needle in model_profiles if needle not in ollama_models]
if missing_models:
    fail("missing Ollama model profile coverage: " + ", ".join(missing_models))

required_behavior = [
    "guard provider.requiresAPIKey else { return true }",
    "editedCredentialProviders.contains($0)",
    "editedCredentialProviders.remove(provider)",
    "failedCloudKeySaveKeepsPriorStoredValueAndAllowsRetry",
    "clearingCloudKeyIsNotUndoneByConnectionTest",
    "CloudAIClientBuildsOllamaChatRequestWithoutAPIKey".lower(),
    "CloudAIClientAttachmentContextFilenamesOnlyWithholdsFileContentsAndFullPaths".lower(),
    "CloudAIClientAttachmentContextNoneWithholdsNamesPathsAndContents".lower(),
    "exportAndImportConfigurationRoundTripsWithoutSecrets",
    "cloudAttachmentContextMode",
    "externalProcessTimeoutMinutes",
    "API keys were not imported or changed",
]
combined_lower = all_text.lower()
missing_behavior = [
    needle for needle in required_behavior
    if (needle if needle == needle.lower() else needle.lower()) not in combined_lower
]
if missing_behavior:
    fail("missing behavior/test guarantees: " + ", ".join(missing_behavior))

for forbidden in [
    "advancedMode",
    "Show advanced controls",
    'Picker("Capability timeout"',
    'Text("Capability timeout (minutos)")',
    '.accessibilityLabel("Capability timeout (minutos)")',
    "minutes (Recommended)",
    "Browse 53",
    "53 user-facing capabilities",
]:
    if forbidden in all_text:
        fail(f"stale or hardcoded Settings/control text found: {forbidden}")

print("Scientific Workbench settings surface check passed.")
PY
