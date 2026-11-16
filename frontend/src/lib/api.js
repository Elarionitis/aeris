/** Typed-ish wrappers over the backend REST API. */

export const API_BASE = (import.meta.env.VITE_API_BASE ?? 'http://localhost:8000').replace(/\/$/, '');

/** Error carrying the HTTP status, so callers can distinguish 404 from 503. */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(path, { signal, method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      signal,
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw new ApiError(`Cannot reach the API at ${API_BASE}. Is the backend running?`, 0);
  }

  if (!response.ok) {
    // FastAPI puts the reason in `detail`; fall back to the raw body.
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === 'string') detail = payload.detail;
      else if (Array.isArray(payload?.detail)) detail = payload.detail.map((item) => item.msg).join('; ');
    } catch {
      /* non-JSON error body: keep the status message */
    }
    throw new ApiError(detail, response.status);
  }
  return response.json();
}

export const api = {
  meta: (signal) => request('/meta', { signal }),
  health: (signal) => request('/health', { signal }),
  wards: (signal) => request('/wards', { signal }),
  forecast: (wardId, hours, signal) =>
    request(`/forecast/${encodeURIComponent(wardId)}?hours=${hours}`, { signal }),
  attribution: (wardId, signal) => request(`/attribution/${encodeURIComponent(wardId)}`, { signal }),
  enforcement: (limit, signal) => request(`/enforcement/priority-queue?limit=${limit}`, { signal }),
  advisory: (wardId, lang, signal) =>
    request(`/advisory/${encodeURIComponent(wardId)}?lang=${encodeURIComponent(lang)}`, { signal }),
  agentTools: (signal) => request('/orchestrator/tools', { signal }),
  ask: (payload, signal) => request('/orchestrator/query', { method: 'POST', body: payload, signal }),
};
