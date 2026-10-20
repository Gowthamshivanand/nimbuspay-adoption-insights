/* Thin fetch wrapper: same contract as the legacy UI (throws the server's `detail` on a non-2xx). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type J = any;

export async function api(path: string, opts?: RequestInit): Promise<J> {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

export const postJson = (path: string, body: unknown) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
