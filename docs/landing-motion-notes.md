# Landing motion research

Research date: 13 October 2026. Scope: the public No Fear Stage landing page, native JavaScript and CSS. These recommendations are adaptations of the primary sources linked below; the proposed timings are project tuning, not claims that the sources prescribe those exact values. No animation library is needed for this scope.

## Source principles

Emil Kowalski uses decelerating movement for marketing-page entrances and responsive interactions. His examples include a small pressed-button scale and explain why slowly accelerating entrances feel sluggish. [The Easing Blueprint](https://animations.dev/learn/animation-theory/the-easing-blueprint).

His CSS transition guide emphasizes short, interruptible feedback and explicitly named transition properties. This supports hover states that reverse cleanly when a pointer leaves. [Transitions](https://animations.dev/learn/css-animations/transitions).

Google's rendering guidance favors `transform` and `opacity` and asks authors to examine the rendering cost of other animated properties. Avoid permanent layers across an entire page. [High-performance CSS animations](https://web.dev/articles/animations-guide).

MDN documents asynchronous viewport observation with Intersection Observer and animation creation with `Element.animate()`. These APIs provide section visibility triggers and finite, cancellable animations without continuously polling scroll position. [Intersection Observer](https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API), [Element.animate](https://developer.mozilla.org/en-US/docs/Web/API/Element/animate).

The user's reduced-motion preference must change the behavior of nonessential motion. [MDN prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion).

## Recommended patterns

| Pattern | Purpose and behavior | Project tuning | Implementation |
| --- | --- | --- | --- |
| Hero choreography | Establish one reading order: title, supporting text, action, then the practice scene. Keep the CTA immediately usable. | 350–520 ms, `cubic-bezier(.22,1,.36,1)`, rise 12–16 px, item delays 60–70 ms, total delay under 280 ms. | Finite CSS keyframes or WAAPI on a few groups after initial render. Animate groups, not individual words. Reserve the scene's dimensions before images load. |
| Section and card reveal | Connect each new section with the page's reading direction. | 420 ms, same ease-out, rise 18 px, adjacent-card delay 50–70 ms. | One Intersection Observer scoped to landing elements. Observe with a small threshold and negative bottom root margin. Animate once, then unobserve. Maintain readable final styles if JS fails. |
| Button and link feedback | Confirm that the next action is available and that a press was received. | Press 150 ms with scale `.97`; hover 160–180 ms with at most a 2 px lift. Use `ease` for color and ease-out for movement. | Explicit CSS transitions; hover movement only inside `(hover: hover) and (pointer: fine)`. Keep a separate high-contrast `:focus-visible` ring. Do not let movement alter hit areas. |
| Real-content scenario switch | If a visitor chooses a practice context, preserve spatial continuity while showing that context's actual explanatory copy. | 200–240 ms, fade plus 6–8 px rise, no delay. | Update the selected/accessible state synchronously, cancel the previous animation, then animate the new panel through WAAPI. Do not delay navigation or synthesize a live recording, transcript, report or user result. |
| FAQ disclosure | Give opened explanatory content a gentle arrival without delaying access. | 180–220 ms, fade plus 4 px rise; disclosure icon rotation 180 ms. | Native `details`/`summary` preserves keyboard semantics. CSS can animate entry and rotate the indicator. Let height update naturally; do not promise a smooth height transition unless measured and tested. |

## Accessible and durable implementation

Read `matchMedia('(prefers-reduced-motion: reduce)')` before creating observers or WAAPI animations. Under reduced motion, show final states immediately and use instant section navigation. Listen for preference changes and cancel active animations. CSS must independently disable entrance transforms, smooth scrolling and decorative transitions under the same media query.

Content is visible by default. JavaScript may use `Element.animate()` with a finite animation, rather than a CSS class that leaves content hidden until an observer succeeds. If a hidden initial CSS state is used instead, restrict it to a successfully initialized observer and reveal focused content immediately. Destroy landing observers when route content is replaced; repeated navigation must not accumulate observers or replay stale elements.

Use a small number of moving groups. Do not animate layout dimensions, large filters or blur backgrounds. Avoid permanent `will-change`, pointer-following light fields, marquee loops and mandatory parallax: they add work without explaining the practice. Keep imagery and decorative layers static once their entrance finishes. The recording screen's existing device, capture and persistence behavior is outside this landing choreography.

## Review checklist

- Inspect desktop and narrow layouts with the real server, not a `file://` copy.
- Verify entrances finish with all text readable, no clipping and no displaced focus indicators.
- Test rapid interaction, route exit/re-entry and preference changes while an animation is running.
- Verify the page remains readable if Intersection Observer or WAAPI is unavailable.
- Emulate reduced motion and check that no section remains hidden and section navigation is instant.
- Check scroll and interaction in browser performance tools; concentrate any further tuning on actual layout/paint work.
- Keep registration separate from logout. Motion must never hide the currently available authentication action or imply that an account has been created.
- Keep the removed example report absent; the landing may explain the real flow but must not restore a fabricated report preview.
