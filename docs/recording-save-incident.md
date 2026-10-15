# Recording save incident, 15 October 2026

One participant using Safari on iPhone saved the speech and first answer successfully. The second answer was recorded for approximately 59 seconds according to client telemetry, but four attempts to upload the same capture failed with HTTP 422 / `MEDIA_INVALID`. The third answer was captured locally but had not entered the serialized upload queue on the server; final report generation never started. These are content-free observations, not a claim that rejected audio is recoverable or complete.

The screenshot shows the generic answer-queue failure notice, so it cannot distinguish media validation failures from transport errors. The maintained decoder has multiple `MEDIA_INVALID` branches (container recognition, decoding/audio track, file access). Rejected temporary uploads are removed in `finally`. Without the original second-answer Blob, current retained server evidence cannot establish which branch failed or prove a specific Safari defect. Historical [WebKit recording bugs](https://bugs.webkit.org/show_bug.cgi?id=212274) are not evidence of this participant's browser version or current failure. No codec workaround or relaxed validation is justified yet.

## Recovery changes

Failed answer queues now name the failed answer and offer original local Blob downloads for all queued answers. For unreadable media the copy asks the user to download copies before continuing rather than prescribing rerecording immediately. Ordinary successful recording flows retain their existing UI.

The authenticated `/#/recording-copies` route provides a separate recovery view. Open it on the same device and browser context, in another tab while the original meeting stays open. It reads only account-scoped local drafts within the existing 24-hour window. It does not resume uploads, start jobs, clear drafts or prune expired entries; the initialization path also skips legacy guest-draft loading. Empty state is not proof that an original open tab has no in-memory recordings. Blob URLs are revoked on navigation/session expiry, and an asynchronous read is ignored after an owner or route change.

Users can download available copies and explicitly share the failed answer with the operator for private diagnosis. No automatic diagnostic upload, public media route or new provider call is added. The route cannot repair missing bytes, retrieve another browser's storage or confirm lexical/capture completeness. Existing original bytes, capture keys and server-acknowledgement retirement rules remain unchanged.

Frontend regression checks cover stage-specific failure copy, original download links, no report start on failed uploads, owner isolation, a read-only draft scan with expired entries, and no upload/job/deletion from the recovery view. Actual browser validation used the separate local fixture origin on port 8095 and a synthetic account. Production recordings and account credentials are not used for tests.
