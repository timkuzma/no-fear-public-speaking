# Question wording rejection, 15 October 2026

The meeting displayed a saved-speech continuation with `AI_WORDING_INVALID`. At investigation time, three question jobs for three accounts had failed at `questions_wording`; two were on 15 October. The referenced saved media/transcripts remained present. The application and both workers were ready. Historical raw editor responses are not retained, so the exact rejected field of each original job is unknown.

A bounded private replay used the saved transcripts/configuration of the two latest affected practices. One generation and one editor request per practice consumed four journalled text attempts, 24,322 input characters and 12,000 reserved output tokens, with no retries or ASR. No practice, report, question, segment or job was updated. One replay succeeded; the other reproduced the error because every editor item echoed both the exact input `source` and `max_chars`. The validator already tolerated an unchanged cap but rejected any source key.

The validator now discards an optional source echo only after exact equality with the original server input. Modified sources, modified caps, unknown keys, missing/duplicate IDs and invalid text still fail. Publication continues to use server-owned provenance; source echoes never become public question fields. Both captured responses pass the corrected validator offline with the same source bindings. This fixes the reproduced compatibility failure; it cannot establish the cause of every historical rejection or guarantee semantic quality. Prompt versions and public schemas are unchanged.

Question-stage errors now say that questions could not be prepared, instead of referring to report wording. Failed jobs remain on explicit user retry; no automatic practice/report regeneration was added.

The same screenshot showed a broken audience image. An external fetch of the 2,191,105-byte PNG returned 200 but timed out after 917,020 bytes in 20 seconds; this does not prove the screenshot's image failure had the same cause. Both renderers now use a same-dimension JPEG derivative (320,773 bytes), preserving the original illustration and provenance. The PNG remains available for cached clients.

Validation: 279 Python tests, frontend module syntax checks, exact captured-response replay and a disposable local browser flow from synthetic speech recording to the first audience question. The audience JPEG loaded in that meeting. Raw replay artifacts stay private in ignored `outputs/question-wording-incident-20261015/`.
