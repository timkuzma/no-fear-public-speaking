# Landing redesign, 13 October 2026

## Implemented behavior

The supplied video is analyzed in `design-reference-analysis.md`; independently researched primary motion sources and tuning are in `landing-motion-notes.md`. The implementation uses a centered dark hero, rounded light scenario section, bright existing virtual-meeting illustration, dark three-step method, native FAQ and closing action. No example report, invented metrics, testimonials or reference branding is shipped.

Guests see separate login and registration links. Authenticated users see practice/history navigation and a separate logout container. Every account-creation button says `Регистрация`. The header logo/wordmark and favicon reference are removed. Practice capture, durable drafts, authentication, ownership and server jobs retain their existing implementation.

Scenario buttons switch explanatory copy and accessible pressed state. They do not set practice configuration; their CTA opens the real one-minute onboarding, which retains custom setup. The hero explicitly prepares a speech **before** meeting an audience, while the product scene is labeled virtual.

The eight short prospect answers from `prospect-faq.md` form the native FAQ. The hero explains guest recording versus account-only AI before its primary action. The invitation condition is rendered from the existing server-provided `registration_requires_invite` value, so local development does not falsely require an invitation. The FAQ privacy link was followed in the browser; its narrow layout and keyboard disclosure were checked under reduced motion.

Animations use finite WAAPI entrances, one-shot Intersection Observer reveals, interruptible context transitions and native FAQ disclosure. Route replacement cancels animations and disconnects observers/listeners. Reduced motion shows final content immediately. No animation library, scroll takeover or continuous decorative loop is added.

Golos Text and Manrope are self-hosted variable fonts, obtained from the official Google Fonts repository (`ofl/golostext`, `ofl/manrope`). Their original OFL license files are included in `public/fonts/`. Existing meeting-image provenance remains in the project asset documentation.

## Practical validation

- Python 3.12 regression suite: **123 passed**. The guest autosave test now expects the requested registration label while still checking persistence and absence of guest provider transmission.
- Node syntax checks: `public/app.js`, `public/api.js`, `public/landing-motion.js`; `git diff --check`.
- Real browser on the isolated loopback fixture: registration heading/submit label, login, authenticated navigation, logout returning to guest navigation, hero CTA opening actual one-minute setup, scenario selection and keyboard Enter opening native FAQ.
- Narrow and desktop layouts checked with temporary viewport/device emulation. Actual DOM width equaled document scroll width, including a very narrow 291 CSS-pixel viewport under browser zoom. Reduced-motion emulation reported zero active animations on the landing and visible content. Desktop hero and full-page screenshots were inspected.
- Normal motion produced the five finite hero entrance groups. Leaving the landing removed their animations; the existing workspace heading animation remains separate. Browser console inspection returned no errors.
- Test accounts and synthetic provider responses stayed in the disposable local fixture. No real AI requests were made for this UI release. This validation does not replace the earlier real-provider acceptance documented in `production-deployment.md`.

## Release

This is a frontend-only release. It reuses the verified immutable backend baseline documented in `production-deployment.md` and replaces `public/` through the existing backup, readiness and rollback controller. The authoritative current/previous image identities remain in the private host release ledger. Proxy configuration and the separately owned `scena` project are outside this change. No Git push is part of this task.

The application source at `861af7c` was deployed to `https://no-fear-stage.157.22.172.204.nip.io/`. The controller returned success with `verified_backup: true`; the active image is `sha256:5347ce38efdfdfeb390a10c49b857886faee7f52df362ad5b6be498eef739d16`, with the previous `sha256:fa173d175705affecbde73f44f117af88f50e0c0717074516825d3d98aa1e67c` retained for rollback. External readiness returned 200 with both workers alive and maintenance disabled. Downloaded JS/CSS/font hashes matched local files. After an initial browser network timeout, HTTPS browser verification succeeded: hero access conditions included invitations, registration exposed the invitation field and requested label, the landing had no horizontal overflow at 1440 CSS pixels and no active animation under reduced motion. No browser console errors were reported. Final screenshots are ignored QA artifacts, not committed application assets.
