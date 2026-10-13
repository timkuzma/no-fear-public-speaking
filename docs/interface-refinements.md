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
