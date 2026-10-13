let csrfToken = null;
export class ApiError extends Error {
  constructor(message, code, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}
async function request(
  path,
  { method = "GET", body, timeout = 120000, signal } = {},
) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const cancel = () => controller.abort();
  if (signal?.aborted) cancel();
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    const headers = {};
    if (body && !(body instanceof FormData))
      headers["Content-Type"] = "application/json";
    if (csrfToken && method !== "GET") headers["X-CSRF-Token"] = csrfToken;
    const response = await fetch(`/api${path}`, {
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
      body:
        body instanceof FormData
          ? body
          : body
            ? JSON.stringify(body)
            : undefined,
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new ApiError(
        "Сервер вернул неожиданный ответ. Попробуй ещё раз.",
        "INVALID_RESPONSE",
        response.status,
      );
    }
    if (
      (response.status === 401 || data.error?.code === "CSRF_INVALID") &&
      !["/auth/me", "/auth/login", "/auth/register", "/auth/reset"].includes(
        path,
      )
    )
      window.dispatchEvent(new Event("session-expired"));
    if (!response.ok)
      throw new ApiError(
        data.error?.message ||
          "Не удалось выполнить действие. Попробуй ещё раз.",
        data.error?.code || "REQUEST_FAILED",
        response.status,
      );
    if ("csrf_token" in data) csrfToken = data.csrf_token;
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      error.name === "AbortError"
        ? path === "/auth/register"
          ? "Не удалось завершить регистрацию. Попробуй войти с указанными почтой и паролем: аккаунт мог уже создаться."
          : path.startsWith("/auth/")
            ? "Ответ не пришёл вовремя. Проверь подключение и попробуй ещё раз."
            : "Ответ не пришёл вовремя. Проверь историю перед повторной попыткой."
        : "Не удалось подключиться. Проверь подключение и попробуй ещё раз.",
      "NETWORK_ERROR",
      0,
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}
export const api = {
  me: () => request("/auth/me", { timeout: 10000 }),
  register: (body) => request("/auth/register", { method: "POST", body, timeout: 15000 }),
  login: (body) => request("/auth/login", { method: "POST", body, timeout: 15000 }),
  logout: async () => {
    const result = await request("/auth/logout", { method: "POST" });
    csrfToken = null;
    return result;
  },
  reset: (body) => request("/auth/reset", { method: "POST", body, timeout: 15000 }),
  completeOnboarding: () =>
    request("/auth/me", {
      method: "PATCH",
      body: { onboarding_completed: true },
    }),
  createPractice: (body) => request("/practices", { method: "POST", body }),
  practices: (offset = 0) => request(`/practices?limit=30&offset=${offset}`, { timeout: 10000 }),
  practice: (id) => request(`/practices/${encodeURIComponent(id)}`),
  liveChunk: (id, file, sessionId, index, offsetSeconds, signal) => {
    const body = new FormData();
    body.append("file", file, "speech-chunk.wav");
    body.append("session_id", sessionId);
    body.append("index", String(index));
    body.append("offset_seconds", String(offsetSeconds));
    return request(`/practices/${encodeURIComponent(id)}/live-chunks`, {
      method: "POST",
      body,
      timeout: 20000,
      signal,
    });
  },
  liveTranscript: (id, sessionId, signal) =>
    request(
      `/practices/${encodeURIComponent(id)}/live-transcript?session_id=${encodeURIComponent(sessionId)}`,
      { timeout: 10000, signal },
    ),
  upload: (id, file, kind, index, liveSessionId, liveChunkCount, clientKey) => {
    const body = new FormData();
    body.append(
      "file",
      file,
      `recording.${file.type.includes("mp4") ? "m4a" : file.type.includes("ogg") ? "ogg" : "webm"}`,
    );
    if (liveSessionId) {
      body.append("live_session_id", liveSessionId);
      body.append("live_chunk_count", String(liveChunkCount));
    }
    body.append("kind", kind);
    body.append("index", String(index));
    if (clientKey) body.append("client_key", clientKey);
    return request(`/practices/${encodeURIComponent(id)}/segments`, {
      method: "POST",
      body,
    });
  },
  startJob: (id, kind, { refresh = false } = {}) =>
    request(`/practices/${encodeURIComponent(id)}/jobs`, {
      method: "POST",
      body: refresh ? { kind, refresh: true } : { kind },
    }),
  job: (id) => request(`/jobs/${encodeURIComponent(id)}`),
  deletePractice: (id) =>
    request(`/practices/${encodeURIComponent(id)}`, { method: "DELETE" }),
  feedback: (id, body) =>
    request(`/practices/${encodeURIComponent(id)}/feedback`, {
      method: "POST",
      body,
    }),
};
