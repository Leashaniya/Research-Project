// Simple, stable id generator (no external deps).
export function createId(prefix = "id"): string {
  // Use crypto.randomUUID when available
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const c = (globalThis as any)?.crypto;
    if (c?.randomUUID) return `${prefix}_${c.randomUUID()}`;
  } catch {
    // ignore
  }

  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

