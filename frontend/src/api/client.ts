// Fetch wrapper for /api/app. Sends the session cookie and echoes the CSRF cookie
// in X-CSRF-Token on every state-changing request (AUTH-5).

export class ApiError extends Error {
  readonly status: number;
  constructor(
    status: number,
    message: string,
    readonly body?: unknown,
  ) {
    super(message);
    this.status = status;
  }
}

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

async function responseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    if (body?.error?.message) return new ApiError(res.status, body.error.message, body);
    if (Array.isArray(body?.detail))
      return new ApiError(res.status, "Please check the form and try again.", body);
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, `Something went wrong (${res.status}).`);
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const form = options.body instanceof FormData ? options.body : undefined;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined && !form) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const csrf = readCookie("cic_csrf");
    if (csrf) headers["X-CSRF-Token"] = decodeURIComponent(csrf);
  }
  const res = await fetch(`/api/app${path}`, {
    method,
    headers,
    credentials: "same-origin",
    signal: options.signal,
    body: form ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
  });
  if (!res.ok) throw await responseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
