export async function request(path: string, options: RequestInit = {}) {
  const response = await fetch(path, {
    ...options,
    signal: options.signal ?? AbortSignal.timeout(15000),
  });
  if (response.status === 401 && path !== "/auth/login") {
    window.location.assign("/login");
    throw new Error("Your session has expired. Please sign in again.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : `Request failed (${response.status}). Please try again.`,
    );
  }
  return response;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await request(path, options);
  return response.status === 204 ? (undefined as T) : response.json();
}
export function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
