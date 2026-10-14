# Local AI setup

Ollama adds local chat and AI-assisted workflow planning. The deterministic
planner and Core scientific capabilities work without Ollama, a downloaded
model, or a cloud API key. A model's answer is advice to review; it is not
scientific validation.

## Check before downloading

1. Open **Settings → Local AI Setup**. Install or open Ollama if needed.
2. Review **Local endpoint**. The default is `http://localhost:11434`; the app
   accepts only HTTP(S) loopback addresses. A custom local port must be between
   1 and 65535. Do not enter credentials in this field.
3. Select a profile or enter an exact name in **Custom Ollama model**.
4. Select **Check**. Read the endpoint result, CLI path, target-model status,
   and the models found at that check. You can copy a listed model name into
   the custom-model field. Check again after changing the name or endpoint.
5. If the model is already present, select **Test Local AI**. A model found by
   the setup check is not proof that a chat request currently succeeds.

## Review resources and confirm the download

The profiles keep the same model identifiers and default as before. The listed
sizes describe approximate model files, not guaranteed download size, installed
space, free-space requirements, or runtime RAM:

| Profile | Model | Approximate model file | Intended starting point |
| --- | --- | --- | --- |
| Compact | `qwen3:1.7b` | 1.4 GB | Try a smaller model for short chat and routing. |
| Balanced | `qwen3:4b-instruct` | 2.5 GB | Default starting point for chat and planning. |
| Stronger | `qwen3:8b` | 5.2 GB | Evaluate a larger model for planning and explanations. |

These are the sizes in the [Compact](https://ollama.com/library/qwen3:1.7b),
[Balanced](https://ollama.com/library/qwen3:4b-instruct), and
[Stronger](https://ollama.com/library/qwen3:8b) listings checked on 2026-10-13.
Tags and their contents can change. Additional files, partial downloads, other
installed models, context length, and other applications affect resources.
The UI displays total installed system memory; this is not available RAM or a
measurement of this model's workload. No minimum RAM or model-quality guarantee
has been established for every Mac.

1. Select **Download Selected Model**. This opens a review sheet without
   starting a download.
2. Review the exact model, local server, approximate file size (unknown for a
   custom model), and network/storage explanation.
3. Select **Download Model** to start, or **Cancel** to leave it unsent. If the
   model or endpoint changes before confirmation, review the request again.
4. The app shows an indeterminate progress indicator and **Cancel Download**.
   It does not calculate a progress percentage from the captured CLI output.
5. After the client stops, run **Check** and **Test Local AI**. A successful
   download command alone does not establish that the configured model responds.

The download CLI uses the reviewed local server through `OLLAMA_HOST`, rather
than silently using another default port. The CLI and the endpoint's Ollama
server fetch model data over the network. Scientific inputs and chat messages
are not included in this download request. Ollama owns model storage and may
retain partial data after client cancellation; the app does not delete it.
Other active app operations must finish before starting the download.

For model storage, runtime memory, and loaded-model inspection with `ollama ps`,
see the [Ollama FAQ](https://docs.ollama.com/faq). The endpoint adapter follows
Ollama's [CLI client configuration](https://github.com/ollama/ollama/blob/main/api/client.go)
and [host parsing](https://github.com/ollama/ollama/blob/main/envconfig/config.go).

## Recover safely

- **CLI unavailable:** install Ollama, then check again. You can still run
  deterministic workflows.
- **Endpoint check failed:** review the address and port; start Ollama if
  appropriate. A failed probe does not prove which component is unavailable.
- **Model absent:** choose a listed installed model, or review a new download.
- **Download failure:** retain the visible CLI error and recheck. A successful
  endpoint probe must not hide the download error.
- **Download cancelled or timed out:** check model availability before retrying.
  Partial data may remain; do not remove other models or original inputs.
- **Slow response or memory pressure:** try a smaller model or deterministic
  planning, reduce the requested context, and inspect the actual workload.

The model resource labels are guidance, not a benchmark. Synthetic regression
tests use a fake CLI and intercepted HTTP responses; they do not establish
download performance or runtime model quality. Visual acceptance, real model
use, and hosted validation need their own evidence.
