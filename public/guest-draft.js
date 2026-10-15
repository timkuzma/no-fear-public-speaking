const DB_NAME = "stage-guest-draft";
const TTL = 24 * 60 * 60 * 1000;

async function transact(mode, operation) {
  const db = await new Promise((resolve, reject) => {
    let settled = false;
    const fail = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(error);
    };
    const timer = setTimeout(() => fail(new Error("Хранилище записи не ответило. Попробуй ещё раз.")), 5000);
    let request;
    try { request = indexedDB.open(DB_NAME, 1); }
    catch (error) { fail(error); return; }
    request.onupgradeneeded = () => request.result.createObjectStore("drafts");
    request.onsuccess = () => {
      if (settled) { request.result.close(); return; }
      settled = true;
      clearTimeout(timer);
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => fail(request.error);
    request.onblocked = () => fail(new Error("Хранилище записи недоступно."));
  });
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("drafts", mode);
      const request = operation(transaction.objectStore("drafts"));
      let settled = false;
      const finish = (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (error) reject(error);
        else resolve(request.result);
      };
      const timer = setTimeout(() => {
        finish(new Error("Хранилище записи не ответило. Попробуй ещё раз."));
        try { transaction.abort(); } catch {}
      }, mode === "readonly" ? 5000 : 30000);
      transaction.oncomplete = () => finish();
      transaction.onerror = () => finish(transaction.error || new Error("Не удалось сохранить запись."));
      transaction.onabort = () => finish(transaction.error || new Error("Сохранение записи прервано."));
    });
  } finally {
    db.close();
  }
}

export const saveDraft = (draft) =>
  transact("readwrite", (store) => store.put(draft, "current"));
export const clearDraft = (clientKey) =>
  transact("readwrite", (store) => {
    const request = store.get("current");
    request.onsuccess = () => {
      if (!clientKey || request.result?.clientKey === clientKey)
        store.delete("current");
    };
    return request;
  });
export async function loadDraft() {
  const draft = await transact("readonly", (store) => store.get("current"));
  if (!draft) return null;
  if (Date.now() - draft.createdAt >= TTL || !(draft.blob instanceof Blob)) {
    await clearDraft(draft.clientKey);
    return null;
  }
  return draft;
}

const recordingKey = (ownerId, practiceId, index) =>
  `account:${ownerId}:${practiceId}:${index}`;

export function saveRecordingDraft(draft) {
  if (!draft.ownerId || !draft.practiceId || !draft.clientKey)
    throw new Error("Не удалось определить владельца записи.");
  return transact("readwrite", (store) =>
    store.put(
      draft,
      recordingKey(draft.ownerId, draft.practiceId, draft.index),
    ),
  );
}

export function clearRecordingDraft(draft) {
  return transact("readwrite", (store) => {
    const key = recordingKey(draft.ownerId, draft.practiceId, draft.index);
    const request = store.get(key);
    request.onsuccess = () => {
      if (request.result?.clientKey === draft.clientKey) store.delete(key);
    };
    return request;
  });
}

export async function loadRecordingDrafts(ownerId, { pruneExpired = true } = {}) {
  if (!ownerId) return [];
  const prefix = `account:${ownerId}:`;
  const drafts = await transact("readonly", (store) =>
    store.getAll(IDBKeyRange.bound(prefix, prefix + "\uffff")),
  );
  const valid = [];
  for (const draft of drafts) {
    if (draft.ownerId !== ownerId) continue;
    if (Date.now() - draft.createdAt >= TTL || !(draft.blob instanceof Blob)) {
      if (pruneExpired) await clearRecordingDraft(draft);
    }
    else valid.push(draft);
  }
  return valid.sort((a, b) => b.createdAt - a.createdAt);
}
