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
export const clearDraft = () =>
  transact("readwrite", (store) => store.delete("current"));
export async function loadDraft() {
  const draft = await transact("readonly", (store) => store.get("current"));
  if (!draft) return null;
  if (Date.now() - draft.createdAt >= TTL || !(draft.blob instanceof Blob)) {
    await clearDraft();
    return null;
  }
  return draft;
}
