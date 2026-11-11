# Repeated requests and one-time approvals

PERF.13 covers overlapping Chat submissions, refreshes, and model
download confirmations. Chat shows Sending while it processes a
submission. During that interval the composer remains editable and
the next draft stays in place. The user can send it after the first
operation completes. This applies to the Send button and keyboard
submission.

Cloud approval applies to the review currently displayed. The app
rechecks the request fingerprint before sending and keeps a changed
request pending for review. Repeated approval or dismissal actions for
an earlier review leave the current review in place. Download approval
is also consumed once. Retrying a finished download requires a new
review of the current model and endpoint.

Matching Ollama setup checks now share one request. A configuration
change retires the old check. A completed download starts a fresh
model-list check so it can observe the result of the download.
The existing environment check shares its active probe. The optional
astronomy refresh now accepts one check at a time.

## Local verification

| Scenario | Result |
| --- | --- |
| GUI Chat with a held loopback response | Enter kept the second draft while Sending was disabled. The fake server recorded one chat request. The second request arrived only after the first response was released and Enter was pressed again. |
| Overlapping Chat submissions | The Swift test observed one request and one pending draft. Submitting after completion sent the draft once. |
| Repeated cloud approval after a review changes | The fake transport observed zero sends for the old review and one for the newly approved review. The tests also covered a changed file preview. |
| Concurrent Ollama setup checks | The fake transport observed one tags request. A separate check after completion brought the count to two. |
| Repeated model download approval | The old approval produced no second recheck. A newly reviewed retry ran the fixture again. A separate test verified a new model-list check after the pull when an earlier check was in progress. |

All 407 Swift tests passed. The isolated GUI check exercised the Chat
path before the final adjustment to the post-download refresh. The
final test suite covers both paths. All requests and downloads in
this verification used local fixtures. The 22 ordinary state files
and preferences digest matched before and after.
