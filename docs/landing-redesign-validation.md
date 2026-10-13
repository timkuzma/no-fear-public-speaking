# Landing redesign, 13 October 2026

## Implemented behavior

The supplied video is analyzed in `design-reference-analysis.md`; independently researched primary motion sources and tuning are in `landing-motion-notes.md`. The implementation uses a centered dark hero, rounded light scenario section, bright existing virtual-meeting illustration, dark three-step method, native FAQ and closing action. No example report, invented metrics, testimonials or reference branding is shipped.

Guests see separate login and registration links. Authenticated users see practice/history navigation and a separate logout container. Every account-creation button says `Регистрация`. The header logo/wordmark and favicon reference are removed. Practice capture, durable drafts, authentication, ownership and server jobs retain their existing implementation.

Scenario buttons switch explanatory copy and accessible pressed state. They do not set practice configuration; their CTA opens the real one-minute onboarding, which retains custom setup. The hero explicitly prepares a speech **before** meeting an audience, while the product scene is labeled virtual.

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
