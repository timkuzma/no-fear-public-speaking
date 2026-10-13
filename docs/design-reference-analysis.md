# Landing reference analysis

## Evidence and scope

The supplied reference is `/Users/timkuzma/Downloads/B2B SaaS Landing Page Design.mp4`, inspected on 13 October 2026. Its frames show a HackerRank landing page. This identifies the visible reference; it does not establish that the clip is the current production site or that its editing effects are implemented in the original browser.

FFprobe reported H.264 video at **2880 × 2160**, **60 fps**, **11.016667 seconds**. There is no audio stream. Mediabunny is not installed in the available runtime, so inspection used FFmpeg from the existing project QA Docker image, without adding dependencies to the application. Six explicit-time frames and eleven overview frames were extracted and visually inspected. Frame files remain under ignored `outputs/test-artifacts/landing-redesign/`; they are inspection artifacts, not website assets. The source video and reference screenshots must not be shipped as our own work.

Explicit-time evidence:

| Time | Frame | Visible composition |
| --- | --- | --- |
| 00:00.0 | [Hero](../outputs/test-artifacts/landing-redesign/at-0.0s.jpg) | Black page, slim navigation, oversized centered statement, green symbols and signup control, one centered main CTA, rounded white next-section edge |
| 00:01.5 | [Framed hero](../outputs/test-artifacts/landing-redesign/at-1.5s.jpg) | Same page scaled into a rounded black device-like frame, outside green glow |
| 00:03.3 | [Scenario cards](../outputs/test-artifacts/landing-redesign/at-3.3s.jpg) | White section, centered heading, two equal dark cards with benefits and small product illustrations |
| 00:05.3 | [Layered feature](../outputs/test-artifacts/landing-redesign/at-5.3s.jpg) | White section, left-side statements, right-side bright portrait photograph, overlapping dark credential card |
| 00:07.4 | [Dark feature](../outputs/test-artifacts/landing-redesign/at-7.4s.jpg) | Black section, large left statement, right-side human photograph and staggered task cards below |
| 00:09.9 | [Return to hero](../outputs/test-artifacts/landing-redesign/at-9.9s.jpg) | Return to initial full-width hero composition, making the short reel loop |

## Composition and information hierarchy

The reference makes typography the dominant object. At 00:00 the main statement occupies approximately the middle two-thirds of the frame width; the description and CTA are much narrower. The hero is centered rather than built as a conventional two-column SaaS template. The thin navigation divider and the low density of navigation elements keep attention on the statement.

The next white section is already visible at the lower edge of the hero. Its large rounded top corners provide a clear change of scene and a reason to scroll. At 00:03.3, a centered heading introduces two parallel routes. Each card contains one audience name, a short explanation, three benefits and a CTA. Both cards are equal in size, but the bright green CTA prioritizes one route. The illustrations occupy the right edge rather than competing with the text block.

At 00:05.3, the layout changes from equal cards to asymmetric explanation: short text on the left and a portrait with a dark UI card on the right. Only the first text statement is strongly emphasized; subsequent statements fade into the background. This appears to communicate a sequential story, but the clip alone cannot prove the site's underlying scroll or interaction mechanics. The person and the interface occupy different layers, with the interface card extending beyond the image's bounds.

At 00:07.4, the surface changes back to black. A large editorial statement sits left, while a portrait anchors the right. A few overlapping task cards explain the product action below the headline. The alternating surfaces create chapter boundaries without adding ornament to every section.

The clip does not show a pricing section, a complete footer, mobile layouts, keyboard behavior, consent implementation, or any authentication flow. Those features must be designed and checked from our actual requirements rather than inferred from this video.

## Typography and color

The visible face is a neutral sans serif with regular-weight display text and tighter large-heading spacing. Its exact font family cannot be reliably identified from compressed video. The hierarchy comes mainly from scale, whitespace and selective emphasis rather than many weights or decorative type styles.

The main palette is black, white, gray and bright green. Dark feature cards have a slight blue/green tint. Green appears in a few words, the primary action and small product details. Photography preserves natural color even when the surrounding section is dark. This is the transferable palette discipline: one strong action color, mostly neutral surfaces, naturally colored human imagery.

The reference's dark gray hero text on black is visually subdued. Our implementation should retain the large editorial hierarchy while making all useful copy readable at normal contrast. Muted inactive statements cannot contain essential information that the visitor needs to discover through motion. Body copy remains at least 16 px, headings wrap naturally, and Russian headings are written as complete connected phrases without forced line breaks.

## Motion visible in the clip

Three different motion layers are visible:

1. **Presentation framing.** During the opening, the entire page scales into a rounded device frame against a green exterior glow. At the end it scales back to the full hero. Because the whole website changes apparent scale, this is likely reel presentation or a framing effect; it is not reliable evidence of useful in-page navigation behavior.
2. **Section travel.** The view moves vertically through the hero, white cards, white feature and dark feature. Transitional frames contain strong directional blur. That blur belongs to the supplied video evidence and should not be imposed on live text while a user scrolls.
3. **Layered content emphasis.** The two scenario cards are briefly vertically offset during entrance, then settle into one row. The feature image and its UI card overlap with different boundaries, suggesting depth and staged entrance. The clip supports using small staggered entrances, but it does not establish exact timing curves, whether scrolling drives them, or whether the original implementation uses pinning.

The appropriate adaptation is small section reveals and subtle card/button response with native scrolling. Avoid scroll hijacking, moving the full document scale, animated layout dimensions, large blur filters and continuous movement near readable text. Do not copy the fingerprint, AI star, HackerRank branding, handwritten arrows, credential UI or cookie overlay. The reference's visible decorative arrow is also incompatible with the project's CTA rules.

## Translation to No Fear Stage

The user's requested logo removal should remove the graphic mark and its decorative identity treatment. A plain navigational home label can remain useful. Public navigation exposes independent **«Вход»** and **«Регистрация»** links. Authenticated navigation exposes practice/history and a separate **«Выход»** account action. The registration form's submit label is **«Регистрация»**. The same label must be used wherever account creation is an action, while prose may explain the account's purpose.

Recommended landing sequence:

| Section | Purpose | Reference principle | Product-specific content |
| --- | --- | --- | --- |
| Editorial hero | Explain the benefit immediately and start a real attempt | Large type, one primary CTA, minimal competing objects | Rehearse before meeting an audience; CTA **«Начать тренировку»**; honest guest continuation note |
| Practice scene | Make the experience understandable | Human imagery plus limited interface depth | Bright existing audience illustration or truthful meeting representation, identified as illustration; no generated analysis, score or invented speech |
| Situations | Help a visitor recognize their task | Parallel scenario cards | Presentation, interview or idea defense, only when existing setup supports these routes; each card explains the specific preparation need |
| Three-step method | Set expectations before recording | Clear chapter transition and short feature statements | Record a speech, answer questions grounded in that speech, choose one recommendation for another attempt |
| Questions and data | Resolve real barriers | Calm readable light surface | Guest recording, same-recording authentication, analysis of transcript content, saved history and deletion |
| Closing action | Offer a clear next step | Strong restrained final surface | Start a one-minute rehearsal; registration remains a separate account action |

The landing must not reintroduce an example report, report preview, fictitious results, fabricated customer names or testimonials. Meeting imagery can explain the recording experience without impersonating a real participant or showing an invented completed report. Avoid overlays across faces. Privacy explanations describe the actual text/audio pipeline and do not claim gesture, emotion or personality analysis.

The redesign preserves the existing guest recording route, the same-Blob account import, durable practice continuation and server-owned history. The implemented scenario switch explains supported contexts; it does not change practice configuration. Its CTA opens the actual existing one-minute onboarding, where custom settings remain available. Landing motion is scoped to the landing; it must not remount, animate or disturb the recording scene.

## Implementation acceptance

- Desktop keeps the large type and contrast-based chapter rhythm. At narrow widths all text, images and cards enter document flow without cropping, face-covering overlays or horizontal overflow.
- Essential content is present without animation and remains visible if JavaScript observers are unavailable. `prefers-reduced-motion` disables entrance travel and continuous decorative motion.
- Reveal effects run once for elements entering view and stop after navigation. Route changes clean up observers and event listeners.
- Keyboard focus is visible on every link, button and FAQ summary. Animations cannot hide a focused control or delay access to it.
- Registration and logout remain separate in actual logged-out and logged-in browser checks. Existing drafts survive account navigation.
- Browser checks cover desktop, mobile, reduced motion and short-height viewport behavior. The redesign does not change the authenticated recording and analysis logic.

This document records video evidence and implementation direction. Final implementation checks and independently researched animation sources belong to the redesign's validation notes.
