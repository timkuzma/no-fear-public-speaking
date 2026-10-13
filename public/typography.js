// Presentation only: stored copy, form values and provider evidence stay unchanged.
const shortWords = "а|и|в|во|к|ко|с|со|у|о|об|обо|от|до|за|из|изо|по|на|не|ни|но|да|то|ли|же|бы|без|для|над|под|при|про|или|как|что|чем|я|ты|он|мы|вы|их|её|его|это";
const wordSpace = new RegExp(`(?<![\\p{L}\\p{N}_])(${shortWords})[ \\t]+(?=[\\p{L}\\p{N}«„“"'(])`, "giu");
const trailingWordSpace = new RegExp(`(?<![\\p{L}\\p{N}_])(${shortWords})[ \\t]+$`, "iu");
const excluded = "script, style, textarea, input, select, code, pre, [contenteditable]:not([contenteditable='false']), [data-typography='off']";
const inlineTags = new Set(["A", "SPAN", "STRONG", "EM", "B", "I", "SMALL", "MARK", "S", "U"]);

export function bindShortWords(text) {
  return text.replace(wordSpace, "$1\u00a0");
}

function inlineContinuation(node) {
  let next = node.nextSibling;
  while (next?.nodeType === 8) next = next.nextSibling;
  if (!next || (next.nodeType !== 3 && !inlineTags.has(next.tagName))) return false;
  return /^[\p{L}\p{N}«„“"'(]/u.test(next.textContent.trimStart());
}

function formatText(node) {
  if (!node.parentElement || node.parentElement.closest(excluded)) return;
  let text = bindShortWords(node.data);
  if (inlineContinuation(node)) text = text.replace(trailingWordSpace, "$1\u00a0");
  // Avoid a self-perpetuating MutationObserver loop.
  if (text !== node.data) node.data = text;
}

export function applyTypography(root) {
  if (root.nodeType === 3) return formatText(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) formatText(walker.currentNode);
}

export function installTypography(roots) {
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "characterData") formatText(record.target);
      // Revisit the parent as a link can follow an existing short word.
      else applyTypography(record.target);
    }
  });
  roots.filter(Boolean).forEach((root) => {
    applyTypography(root);
    observer.observe(root, { childList: true, characterData: true, subtree: true });
  });
  return () => observer.disconnect();
}
