// A laptop-hosted backend is shared through a Cloudflare quick tunnel whose URL changes on every start, so the
// deployed site accepts it as ?api=https://<name>.trycloudflare.com (kept for the tab). Only tunnel hosts pass, so a
// crafted link cannot point this site at an arbitrary server.
const TUNNEL = /^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/;

function apiUrl(): string {
  if (typeof window !== "undefined") {
    try {
      const param = new URLSearchParams(window.location.search).get("api")?.replace(/\/$/, "");
      if (param && TUNNEL.test(param)) window.sessionStorage.setItem("yokoten-api", param);
      const saved = window.sessionStorage.getItem("yokoten-api");
      if (saved && TUNNEL.test(saved)) return saved;
    } catch {}
  }
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

export const API_URL = apiUrl();

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function roleHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const role = window.localStorage.getItem("yokoten-role");
  return role ? { "X-Role": role } : {};
}

export const WAKING_UP = "The backend is offline or waking up - try again in ~30 s.";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
        ...roleHeader(),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError(0, WAKING_UP);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export { roleHeader };
