# Interface refinements, 13 October 2026

## Behavior

`public/typography.js` formats rendered text nodes with nonbreaking spaces after short Russian prepositions, conjunctions, particles and selected short pronouns. It observes the application and toast roots, including late questions, report content and errors. Form values, code, editable regions, stored transcripts and provider evidence remain unchanged. Explicit newlines are preserved. No HTML rewriting is used.

Landing scenario descriptions occupy the same CSS grid cell. Hidden descriptions reserve the largest content height but remain absent from the accessibility tree. Their CTA is a persistent sibling outside the animated content. Only the selected description animates; no fixed pixel height or viewport-specific copy duplication is needed.

The pilot-version footer label and the two requested meeting-image captions are removed. The privacy page, its links and the expanded registration conditions are removed; legacy `#/privacy` links redirect to the landing. The consent checkbox is also removed at the user's explicit request. Registration omits `consent`, which defaults to false in the API; no invisible acknowledgement is submitted. The historical database field remains compatible with explicit legacy values and is no longer an upload gate. Authentication, ownership, origin, CSRF, invitations and provider limits retain their existing checks. No database schema migration is needed.

## Validation

- Regression suite: 124 passed. Core API tests register without the consent field, assert its stored false value, and exercise ordinary and live recording uploads. Separate syntax checks cover the frontend modules and Python app.
- Isolated local fixture: registration without consent, audio upload and a completed synthetic report succeeded. No actual provider request was made.
- Browser inspection covered registration, login/reset, guest setup, landing, history, saved report and question chat. At 320 CSS pixels, text-range measurements found no separated short-word pairs or horizontal overflow. Typed form values retained normal spaces.
- Scenario switching across all three modes at 320, 375, 1024 and 1440 CSS pixels produced identical CTA document coordinates within each viewport. All widths had document scroll width equal to viewport width. Reduced motion remained functional.
- Browser confirmed no public privacy links, no pilot label, no registration consent control and the old privacy-route redirect.

## Release compatibility

This release changes server registration behavior as well as public assets; it must copy both `server/` and `public/` into the verified application image. Replacing public assets alone would leave registration broken.

Automatic pre-activation recovery remains compatible: maintenance prevents new registrations before promotion. For a later UI rollback, retain this server behavior and restore only the previous public assets. An older server image would reject uploads from new accounts whose historical consent flag is false. Do not fabricate consent flags to make old code accept those accounts; build a rollback image with the current server instead. Code rollback must preserve current database/media as before.

## Required account and registration completion

Following the user's subsequent correction, every public start CTA now leads to registration; `#/guest` redirects to registration or authenticated setup. The anonymous recording action is guarded, and the offline screen no longer offers a guest bypass. Existing guest drafts are still recoverable after authentication. README and landing answers describe the current required-account entry.

Registration/login now receive provider/invitation flags in their successful response. The client no longer waits for another `/auth/me` after account creation. Success displays an explicit progress message before opening setup. Auth requests have 10–15 second bounds; registration timeout copy explains that an account may already exist and offers signing in instead of blindly resubmitting. Form failures retain values and re-enable submission. IndexedDB open/read operations have five-second bounds; writes have a 30-second bound. A late open closes its connection, and a timed-out transaction aborts without discarding the original recording Blob.

An independent fixture origin (`127.0.0.1:8095`) verified actual browser registration to setup, logout, direct guest-route rejection and duplicate-registration error recovery. This avoids changing the session of a user viewing localhost:8094. Node regression checks cover stalled API/IndexedDB operations, late connection cleanup, removal of the redundant session request, retained fields, and required-account navigation. They use synthetic data and make no provider calls.

## Published verification

Source `a8ce99a` (including preceding interface changes at `e4193e1`) is deployed at `https://no-fear-stage.157.22.172.204.nip.io/`, image `sha256:2f28d5d14140d2c8bf2a7a9aaf4be76cf2fbd7b05114394307de1ab4106a0335`. The release controller returned success with a verified pre-activation backup. External readiness returned 200, both workers were alive, and maintenance was disabled. Public HTML, JS and CSS hashes matched local files.

The final regression suite passed 125 tests; a subsequent focused backend/auth check passed 20 tests. Actual HTTPS acceptance created a disposable account through a one-use fixture invitation without a consent field, verified Secure/HttpOnly/SameSite Strict cookies and the complete session envelope, then exercised logout/login and anonymous private-endpoint denial. Operator verification confirmed the stored consent flag was false. Only this synthetic account/session and its invitation were removed after acceptance; participant accounts and invitations were untouched. No provider request was made.

The HTTPS browser redirected `#/guest` to registration, with no guest/privacy links or consent control. The corrected registration heading and invitation field were visible. Temporary viewport/reduced-motion overrides were reset after screenshots. Production invitations remain required; this release changes anonymous practice entry, not invitation issuance.

The default previous image is the `e4193e1` release, which already supports false historical consent values. A separate older-interface rollback image with compatible server behavior is also available as `no-fear-stage:e4193e1-rollback-ui` (`sha256:fe7a77037ec5a4c7458b4eecdcb0c94689f1bb3412c9e579fa3bacb82bc07afe`). Very old server images predating consent-control removal still need the compatibility procedure above. No Git push was performed.

## Product FAQ publication, 13 October 2026

The seven preparation-focused FAQ pairs from source `bf1be1f` are published in image `sha256:81c735e02bed6dc1352964d8bf3036d78eea4a9b062e4870c96fb16a2d4bbc31`. This image reuses the exact verified `a8ce99a` backend image above and replaces only public assets; the previous image retained for rollback is `sha256:2f28d5d14140d2c8bf2a7a9aaf4be76cf2fbd7b05114394307de1ab4106a0335`. Registration, historical consent handling, data and runtime settings are unchanged.

The controller reported success with a verified backup. External readiness returned 200 with both workers alive and maintenance disabled. Public HTML and app.js hashes matched `bf1be1f`; HTML references `app.js?v=20261013-product-faq`. The public source and rendered page contained all seven new questions.

HTTPS browser checks verified Enter disclosure, readable 16px answers, 1440 and 375 CSS-pixel layouts without horizontal overflow, and working disclosure under reduced motion with zero active animations. No browser console errors were reported. The landing still had no guest or privacy links. Screenshots are ignored artifacts under `outputs/test-artifacts/product-faq/`. Node syntax checks and diff whitespace checks passed; this copy-only release did not repeat backend/provider testing or make AI calls. No Git push was performed.

## Hero scroll-link removal, 13 October 2026

Source `6f5de35` is published in image `sha256:cfb218949fdf6a3e47d8d72781f2f83d66e99c794482d42a3a91ec60317fe14a`, using the exact previous FAQ image as its backend base. The hero rehearsal-scroll button, unused action handler and CSS rules are absent. HTML references both app.js and landing.css with version `20261013-hero-cleanup`.

The controller succeeded with a verified backup; external readiness returned 200 with both workers alive and maintenance disabled. Public HTML/JS/CSS hashes matched `6f5de35`. The HTTPS browser confirmed no removed phrase/button in the hero, the main CTA still requires registration, all seven FAQ questions remain, and 1440/375 CSS-pixel layouts have no horizontal overflow. Browser console inspection found no errors. Node syntax and diff checks passed; no backend/provider tests were repeated. The previous image `sha256:81c735e02bed6dc1352964d8bf3036d78eea4a9b062e4870c96fb16a2d4bbc31` is retained for rollback. No Git push was performed.

## Feedback on the user's own speech

The first-minute card and setup guide no longer prescribe a project topic, problem/solution structure, beneficiary or example. Both starter paths submit empty topic and criteria. Custom setup also permits an empty topic; unnamed practices render a neutral heading. Explicit user criteria and selected post-report recommendations remain available. Existing recordings and practice configurations are retained.

Landing scenario/FAQ copy no longer instructs users to supply particular speech elements before recording. The shared provider rule tells question/report generation to use actual speech and its purpose/genre, treating scenario/topic as context rather than mandatory content. Missing problem, solution, benefit or example is not by itself a deficiency. Unrequested report criteria are still discarded by server validation; this cannot guarantee every model recommendation's quality.

Validation: 125 tests passed. Frontend regression checks exercise actual starter/custom-submit actions with empty topic/criteria and preservation of explicit user choices. Mocked provider checks verify empty criteria/context delivery, unchanged transcript and rejection of unsolicited criteria. Browser checks on an isolated fixture origin covered registration, the first-minute entry and a custom free-speech entry with both optional fields blank; both opened the meeting with a neutral heading and no content checklist. No console errors or real provider requests occurred.

Source `ae49a61` is published at `https://no-fear-stage.157.22.172.204.nip.io/` in image `sha256:e14bfca4d31a9ed8958dee9730214a1d87f3aee02b28d4debb011d3ddef1314d`. Both public assets and server code were copied into the previously verified image. The controller succeeded with a verified backup; the prior `sha256:cfb218949fdf6a3e47d8d72781f2f83d66e99c794482d42a3a91ec60317fe14a` image remains available for rollback. External readiness returned 200, both workers were alive and maintenance was disabled. Public HTML/JS hashes and the active container's AI-module hash matched local source. The HTTPS browser displayed the revised defense-context copy and reported no console errors. Local setup at 375 CSS pixels had no horizontal overflow and no required topic field. No Git push or real-provider acceptance run was performed.
