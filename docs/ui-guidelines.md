# Interface review and asset provenance

These rules apply to every maintained route in `public/` and are summarized in root `AGENTS.md`.

## Maintained interface rules

- The header has no logo/wordmark. Guests have separate login and registration links; authenticated users have practice/history navigation and a separate logout action. Account-creation CTA labels are `Регистрация`.
- Starting a practice requires authentication. Legacy `#/guest` links lead to registration or authenticated setup; existing guest drafts remain importable after login. Old `#/example` and `#/privacy` links return to the landing. There is no public example report or consent step.
- Preserve native keyboard-accessible selects, an 18px inner chevron gutter and 52px reserved text padding. Headings wrap naturally without terminal periods; CTA labels have no decorative arrows. Use shared typography tokens and inline optional-field labels with attached hints. Keep substantive recommendations as body text beneath a section heading.
- `public/typography.js` formats rendered text nodes across route changes and late updates. It preserves explicit newlines and excludes form values, code, editable regions, stored transcripts and provider evidence.
- Scenario descriptions share one CSS grid cell so the tallest text reserves space. The CTA is a persistent sibling outside the animated copy; context switching must not recreate or move it.
- Landing sections, headings, images and large cards stay visible and static while scrolling. Keep motion tied to explicit interactions, honor reduced motion and clean up animations/listeners on route exit. Current guidance and primary sources are in [landing-motion-notes.md](landing-motion-notes.md).
- Successful registration/login responses already contain provider/invitation flags and CSRF state; do not wait for a redundant session request. Bound auth and IndexedDB operations, preserve form values and keep original recording Blobs on failure. API behavior is in [api-contract.md](api-contract.md).

## Fonts and design reference

Golos Text and Manrope are self-hosted variable fonts sourced from the official Google Fonts repository (`ofl/golostext`, `ofl/manrope`). Their OFL licenses remain beside the files in `public/fonts/`.

The supplied 13 October 2026 design-reference clip showed a HackerRank landing page. Its composition informed the redesign; the clip, reference screenshots, branding and testimonials are not application assets. The implemented page uses its own product copy, generated meeting imagery and native controls.

## Landing image

- Asset: `public/audience-russian-campus-bright.jpg` (JPEG delivery copy of the generated PNG).
- Generated with the built-in `image_gen` tool on 2026-10-11; no third-party photo was downloaded or used as an identity reference.
- This is a fictional photographic illustration of a Russian university context. It does not document real students, identify anyone's nationality, or supply product testimonials. The image alt text explicitly identifies it as an illustration.
- The retained image files in `public/` include unused source variants. Root prototype copies are not part of the application.

### Generation prompt

Use case: photorealistic-natural. Asset type: website landing hero, vertical 4:5 composition. Create an editorial photographic illustration of a small audience listening to a student project defense at a contemporary Russian university in Moscow. Around twelve Russian students and young professionals aged 20–35, predominantly typical local Eastern European appearances with natural individual variety, ordinary contemporary Russian campus clothes, no staged corporate stock smiles. Warm, attentive, relaxed expressions, plausible candid poses and anatomically accurate hands. Camera from the speaker's position, looking towards the audience. Faces of a few people clearly recognizable, not a giant crowd. Simple light university lecture room with timber desks, soft daylight, muted warm cream and olive tones to fit a calm practice product. Natural documentary camera texture. No text, no logos, no flags, no watermarks. This is a fictional generated illustration, not a picture of identifiable real people.

## Bright hero revision

- Edited the generated campus illustration with built-in `image_gen` on 2026-10-11 to use brighter daylight, natural colors, light blue/cream/green clothing and engaged, friendly expressions. The earlier generated asset remains available as an unused source. The delivery JPEG only changes format/compression.
- Keep the generated assets bright and naturally colored. Do not place copy across faces or introduce an example report or recommendation preview on the landing.

### Edit prompt

Use case: lighting-weather / photorealistic-natural. Edit this generated photographic illustration for the hero of a Russian public-speaking practice product. Keep the same contemporary Russian university lecture-room setting, tiered wooden desks, recognizable Moscow university skyline, portrait composition and same small student audience. Make the atmosphere noticeably bright, fresh, warm and optimistic: abundant soft spring daylight, light cream walls, natural luminous skin tones, clear colors, fresh blue, cream and light green clothing accents rather than a sea of dark brown and black. Lift shadows without washing out detail. Audience expressions should convey engaged, friendly curiosity and subtle natural smiles, relaxed open posture; nobody looks exhausted, bored or melancholy. Preserve plausible anatomy, candid editorial photography, realistic textures and natural faces. No exaggerated laughing, staged thumbs up, corporate stock-photo posing, orange grading, muted sepia or gray/olive filter. Keep faces clear in the central part of the composition for a website crop. Do not add text, UI overlays, badges, logos, watermarks or other new objects. Output just the edited photographic illustration.

## Meeting scene and chat (2026-10-11)

- `public/audience-meeting-v1.png`: separately generated with built-in image_gen, no downloaded photo or identity reference. Chat participant names are fictional labels for generated questions, never live people. Fictional listeners in a contemporary Russian university/workplace meeting room, directly facing the speaker. This is an illustration, never a testimonial. The landing image is unchanged.
- Keep one immersive scene, a small optional self-video, and one microphone/camera/recording toolbar. No speech-coaching copy or audience caption. Questions appear sequentially in the same chat; each answer starts immediately. Preserve the meeting DOM during background saves and label server persistence only after acknowledgement.
- Keep scene, preview and timer stable during question generation, recording, upload and retries. Reduced motion disables decorative transitions.
- Benchmarks: [Zoom in-meeting chat](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0064400), [Prompt Motion UI states](https://prompt-motion.com/twoclipping-5cba86), [Prompt Motion chat walkthrough](https://prompt-motion.com/wani-shola-16ca7a), [Emil Kowalski on animation speed](https://emilkowal.ski/ui/you-dont-need-animations), [MDN log role](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/log_role). Adapt timing and state continuity, not promotional montage. Scroll-world's scroll-linked video mechanics do not help this recording flow.
