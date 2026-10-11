# Interface review and asset provenance

These rules apply to every maintained route in `public/` and are summarized in root `AGENTS.md`.

| Before                                                           | After                                                                                        | Why                                                            |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Native select arrow flush with the edge                          | Native keyboard-accessible select with an 18px chevron gutter and 52px reserved text padding | Consistent spacing without replacing the native control        |
| Forced line breaks and fragmentary headings with periods         | Complete naturally wrapping headings without terminal periods                                | Readable Russian product copy                                  |
| Decorative CTA arrows, status dot and padded numbering           | Text-only CTA labels and ordinary ordered step numbers                                       | Apply the user's interface preferences consistently            |
| Optional hint on a separate row; adjoining fields visually merge | Inline optional label, grouped field hints and shared typography tokens                      | Keep label, value, description and action hierarchy clear      |
| Long generated recommendations styled as headings                | Section heading followed by the complete recommendation as body text                         | Preserve substantive report text and correct heading semantics |

## Landing image

- Asset: `public/audience-russian-campus-bright.jpg` (JPEG delivery copy of the generated PNG).
- Generated with the built-in `image_gen` tool on 2026-10-11; no third-party photo was downloaded or used as an identity reference.
- This is a fictional photographic illustration of a Russian university context. It does not document real students, identify anyone's nationality, or supply product testimonials. The image alt text explicitly identifies it as an illustration.
- The imported legacy images remain unused by maintained routes.

## Validation

- Checked landing, registration, login, password reset, guest setup, example report, privacy, authenticated setup, history and a saved real AI report in the live browser.
- No terminal heading periods, forced heading breaks, arrow CTA labels, decorative status dots or padded step numbers were found on the eight static routes and the saved report.
- Landing, registration, authenticated setup and example report fit a 390 CSS-pixel viewport without horizontal overflow. Viewport overrides were reset after the check.
- Native keyboard selection changed duration from 5 minutes to 3 minutes using Space, ArrowUp and Enter. Computed select padding is 52px; chevron gutter is 18px. Labels, values and hints use 14px, 16px and 13px respectively.
- Both frontend modules pass Node syntax checks. Formatting and Git whitespace checks pass. No backend contract or stored practice content was changed.

### Generation prompt

Use case: photorealistic-natural. Asset type: website landing hero, vertical 4:5 composition. Create an editorial photographic illustration of a small audience listening to a student project defense at a contemporary Russian university in Moscow. Around twelve Russian students and young professionals aged 20–35, predominantly typical local Eastern European appearances with natural individual variety, ordinary contemporary Russian campus clothes, no staged corporate stock smiles. Warm, attentive, relaxed expressions, plausible candid poses and anatomically accurate hands. Camera from the speaker's position, looking towards the audience. Faces of a few people clearly recognizable, not a giant crowd. Simple light university lecture room with timber desks, soft daylight, muted warm cream and olive tones to fit a calm practice product. Natural documentary camera texture. No text, no logos, no flags, no watermarks. This is a fictional generated illustration, not a picture of identifiable real people.

## Bright hero revision

- Edited the generated campus illustration with built-in `image_gen` on 2026-10-11 to use brighter daylight, natural colors, light blue/cream/green clothing and engaged, friendly expressions. The earlier generated asset remains available as an unused source. The delivery JPEG only changes format/compression.
- Removed the desaturation filter, the dark overlay across faces and its context-free copy. The remaining card is explicitly labeled as an example recommendation. Shared background colors are lighter; text contrast and layout tokens remain intact.

- Verified the final hero in the live browser: updated image loaded, no overlay caption, no image filter and no horizontal overflow at the current desktop viewport. Both JavaScript modules pass syntax checks; Git whitespace checks pass.

### Edit prompt

Use case: lighting-weather / photorealistic-natural. Edit this generated photographic illustration for the hero of a Russian public-speaking practice product. Keep the same contemporary Russian university lecture-room setting, tiered wooden desks, recognizable Moscow university skyline, portrait composition and same small student audience. Make the atmosphere noticeably bright, fresh, warm and optimistic: abundant soft spring daylight, light cream walls, natural luminous skin tones, clear colors, fresh blue, cream and light green clothing accents rather than a sea of dark brown and black. Lift shadows without washing out detail. Audience expressions should convey engaged, friendly curiosity and subtle natural smiles, relaxed open posture; nobody looks exhausted, bored or melancholy. Preserve plausible anatomy, candid editorial photography, realistic textures and natural faces. No exaggerated laughing, staged thumbs up, corporate stock-photo posing, orange grading, muted sepia or gray/olive filter. Keep faces clear in the central part of the composition for a website crop. Do not add text, UI overlays, badges, logos, watermarks or other new objects. Output just the edited photographic illustration.

## Meeting scene and chat (2026-10-11)

- `public/audience-meeting-v1.png`: separately generated with built-in image_gen, no downloaded photo or identity reference. Chat participant names are fictional labels for generated questions, never live people. Fictional listeners in a contemporary Russian university/workplace meeting room, directly facing the speaker. This is an illustration, never a testimonial. The landing image is unchanged.
- Keep one immersive scene, a small optional self-video, and one microphone/camera/recording toolbar. No speech-coaching copy or audience caption. After confirmed upload, questions arrive in a side chat and answers are marked saved only after server confirmation.
- Plain CSS: chat panel 220 ms ease-out; question messages 180 ms with 0/60/120 ms offsets only on completed generation, not on reload. Keep scene, preview and timer stable. Existing reduced-motion rule disables animations.
- Benchmarks: [Zoom in-meeting chat](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0064400), [Prompt Motion UI states](https://prompt-motion.com/twoclipping-5cba86), [Prompt Motion chat walkthrough](https://prompt-motion.com/wani-shola-16ca7a), [Emil Kowalski on animation speed](https://emilkowal.ski/ui/you-dont-need-animations), [MDN log role](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Reference/Roles/log_role). Adapt timing and state continuity, not promotional montage. Scroll-world's scroll-linked video mechanics do not help this recording flow.
