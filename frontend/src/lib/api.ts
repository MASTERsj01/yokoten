export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

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

export const WAKING_UP = "The backend is waking up or offline (free hosting sleeps when idle) - try again in ~30 s.";

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
