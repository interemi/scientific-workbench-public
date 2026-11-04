# Local model setup: acceptance review, 2026-11-04

Source `3a0e8ea` was exercised with the executable built from `d271065`;
only documentation differs between those commits. The executable SHA-256 was
`12bd7a547af5acb3d9812011ae154ff533804312d90ec4d9a15da7905ec15452`.
The test reused the isolated app bundle on the maintainer's macOS 27.0.1
Apple Silicon Mac and the existing Ollama CLI, version **0.40.14**.

## Isolation and review

A temporary second Ollama server listened on a separate loopback port with
its own `OLLAMA_MODELS` directory. `OLLAMA_NO_CLOUD=1` disabled its cloud
features, and `OLLAMA_NOPRUNE=1` retained its model data. The usual Ollama
server and model store were left in place. The test app used isolated
preferences with secret loading disabled.

The model and endpoint were selected in **Local AI Setup**. The temporary
server initially had no models. The first **Review model download** sheet
identified the model, local server, network download, storage effects, and
model-free deterministic route. Cancelling that sheet left zero model files
and zero installed models: review alone did not start a download.

## Real download and cancellation

The first confirmed request downloaded the official
[Qwen3 0.6B model](https://ollama.com/library/qwen3:0.6b). The UI showed
**Downloading model; percentage unavailable**, disabled model/endpoint editing,
and offered **Cancel Download**. It completed before the cancellation action
could be taken; this attempt therefore establishes completion, not cancellation.

The temporary server then listed `qwen3:0.6b`, size **522,653,767 bytes**, with
model digest
`7df6b6e09427a769808717c0a93cadc4ae99ed4eb8bf5ca557c90846becea435`.
The canonical v2 manifest matched that digest, and all five referenced config
and layer blobs matched their recorded sizes and SHA-256 values. Verification
followed the v2 manifest reference used by this
[Ollama version](https://github.com/ollama/ollama/blob/v0.40.14/manifest/manifest.go);
its separately serialized legacy compatibility manifest has different bytes.

A second reviewed request selected
[Qwen3 1.7B](https://ollama.com/library/qwen3:1.7b) at the same isolated
endpoint. Its review showed the approximate 1.4 GB model size and additional
disk/RAM requirements. While its actual download was active, **Cancel Download**
stopped the owned client. The app reported cancellation and warned that partial
data could remain. Recheck listed only the completed 0.6B model and identified
1.7B as not installed. Fifteen partial files remained; their size, allocated
blocks, and modification times were stable across subsequent observations.
No pull client remained active.

The progress presentation is deliberately indeterminate. This review does not
establish an accurate percentage, remaining-time estimate, download speed,
model fitness for a scientific workload, or inference quality.

## Deterministic work with the selected server unavailable

After the cancellation checks, the temporary server was stopped normally.
Local AI Setup reported that the selected endpoint was not reachable. With
that endpoint still selected and no cloud keys loaded, Dashboard prepared a
new synthetic table, and **Run Capability** completed the actual Core backend.
The result had **3 rows and 4 columns**, `app_status: PASS`, unchanged input
hashes, and matching output sizes/hashes in its manifest. Its Job ID was
`D1106BEA-01A8-4655-8FB3-FE886F6EDD02`. Human scientific review remained
incomplete. No model inference request was made in this test.

## Preservation and scope

Seventeen existing model-store file entries retained their size, modification
time, inode, and manifest hashes. Existing Ollama identity-file metadata was
also unchanged. The temporary server and the isolated test app were closed;
the usual server was not stopped. Completed model data and cancelled partial
data remain in the dedicated test directory outside Git. A separate diagnostic
archive retains logs, the installed manifest, and the table run without copying
the model payloads into the repository or a release.

Screenshots, accessibility observations, launch/environment records, file
fingerprints, cancellation observations, and verification results remain
outside Git. This provides local P1.11 acceptance evidence for review-before-
download, real download state, cancellation, recheck, and a model-free Core
route. It does not establish use on another Mac, independent usability,
universal Ollama-version compatibility, or a fresh Python installation.
Full Phase 4 quality/bundle checks, coherent public integration, and hosted CI
for the exact candidate remain pending.
