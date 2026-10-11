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

- Asset: `public/audience-russian-campus.jpg` (JPEG delivery copy of the generated PNG).
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
