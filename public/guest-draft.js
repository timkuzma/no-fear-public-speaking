const DB_NAME = "stage-guest-draft";
const TTL = 24 * 60 * 60 * 1000;

async function transact(mode, operation) {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("drafts");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("Хранилище записи недоступно."));
  });
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("drafts", mode);
      const request = operation(transaction.objectStore("drafts"));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
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

export async function loadRecordingDrafts(ownerId) {
  if (!ownerId) return [];
  const prefix = `account:${ownerId}:`;
  const drafts = await transact("readonly", (store) =>
    store.getAll(IDBKeyRange.bound(prefix, prefix + "\uffff")),
  );
  const valid = [];
  for (const draft of drafts) {
    if (draft.ownerId !== ownerId) continue;
    if (Date.now() - draft.createdAt >= TTL || !(draft.blob instanceof Blob))
      await clearRecordingDraft(draft);
    else valid.push(draft);
  }
  return valid.sort((a, b) => b.createdAt - a.createdAt);
}
