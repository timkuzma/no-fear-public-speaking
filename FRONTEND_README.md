# Сцена без страха — frontend MVP

A dependency-free Russian speech practice frontend. Source and deployable files live in `dist/`.

## Implemented

Ten views: home, scenario, settings, device check, speech, three audience questions, processing, result, details, local history. Desktop/mobile layouts. Native microphone and camera permissions, audio level check, 3–2–1 countdown, actual MediaRecorder capture, elapsed timer, video/audio playback, recording download, actual segment seek markers. Microphone required; camera optional after explicit check. Permissions/capture require HTTPS or localhost. No recording is uploaded. LocalStorage keeps only attempt metadata and demonstrative results; media remains in the current tab's memory. History is capped at 100 entries. Browser reload closes the media session.

## Backend integration boundary

`dist/api.js` exports an adapter and clearly marked example result. Replace its two methods while keeping the UI interface:

- `getQuestions(config) -> Promise<string[]>`: scenario (`speech | defense | free`), topic, duration in minutes, questions boolean. Current questions are generic demonstrations. If backend questions must depend on the actual speech, extend this method to accept the captured speech/attempt ID and finalize/upload the speech segment before asking questions; the current recorder records continuously until all answers end.
- `analyze({config, recording: Blob, segments}) -> Promise<Result>`: full media and real segment boundaries in seconds. Each segment contains `{type: 'speech' | 'answer', start, end, question?}`. Upload the Blob with multipart or a signed upload URL; keys and AI credentials belong only on the backend.

`Result` currently contains `{demo, insight, metrics: [{title,text,label}], strengths: [{title,text}], recommendations: [{title,text}]}`. Coordinate the result/error schema with the other developer before replacing the adapter. The current result screens deliberately always say that AI is not connected: remove/condition those labels when introducing verified real results. Implement attempt IDs, asynchronous job polling, authenticated history and storage as needed on the backend. No endpoints or transport have been assumed.

## Local run and checks

Serve `dist` with any HTTP static server for UI review. Devices require a trustworthy origin (HTTPS or localhost). Open `index.html` through a server, not file://. Static Sites hosting uses `.openai/hosting.json`.

Check JavaScript syntax using `node --check dist/app.js` and `node --check dist/api.js`. `tests/flow.test.mjs` exercises state transitions and recording with deterministic fake devices; this verifies application logic, not hardware compatibility. Real microphone/camera and supported browser testing remains required before release.

WebMCP is feature-detected and exposes only reading state and opening scenario setup, with the same validation/state as UI. It never starts device capture.

## Optional criteria

`config.criteria` is an optional plain-text string (up to 2000 characters), included in the same configuration passed to both API methods. Empty means no custom criteria. The settings screen offers adding or skipping; skip excludes the draft from configuration. Criteria persist in attempt history and repeat configuration. Older attempts without the field remain valid. The demo does not assess criteria. After real AI integration, forward these user-provided criteria as task input and only display verified assessment from the backend.

Three selectable scenarios: public speaking (`speech`) uses the approved large auditorium; defense (`defense`) uses the original eight-listener scene and defaults to questions; free practice (`free`) has optional topic and no questions and retains the smaller scene. Pitch is removed from selection. Legacy browser-history attempts with `pitch` remain accessible; repeating them maps to `speech` while preserving other settings. The scene remains the same for speech and its subsequent questions. No distinct scoring is claimed.

## Registration UI (backend not connected)

Header “Регистрация” opens email/name/password → role selection (school, student, working, exploring, other). Guest practice remains available throughout. Name: 2–80 characters, email: up to 254, password: 8–128. Password exists only transiently in JS memory and the password field; never localStorage, history, files, WebMCP state or logs. Navigating out of registration clears all registration values. Refresh loses the draft. `api.register({email,name,password,role})` deliberately rejects with `AUTH_NOT_CONFIGURED`; UI honestly reports that no account was created and offers guest practice. Do not interpret completed onboarding as authentication.

Replace the method with a HTTPS backend implementation that establishes an authenticated session and returns `{user:{id,name,email,role}}`. Backend must independently validate fields, hash passwords, handle account conflicts, abuse protection, session cookies and CSRF, and implement login/logout/session recovery/reset/verification. Account-backed history is separate future work; current attempt history remains guest browser-local. The registration form is not an implemented login form for existing accounts.
