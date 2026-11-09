// Browser-side storage (IndexedDB) for two things, both kept only on this computer:
//   * the wizard draft: the chosen file(s) and choices, so going back or refreshing does not lose
//     them (up to DRAFT_LIMIT bytes);
//   * saved reports: a snapshot of each finished analysis, so it can be reopened later even after
//     the server data has changed (up to HISTORY_LIMIT bytes, oldest removed first).
// Every call is wrapped: if storage is unavailable (private window, blocked), the app still works.

export const DRAFT_LIMIT = 200 * 1024 * 1024;
export const HISTORY_LIMIT = 1024 * 1024 * 1024;

const DB = "socassess";
const VERSION = 1;

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("draft")) db.createObjectStore("draft");
      if (!db.objectStoreNames.contains("history")) db.createObjectStore("history", { keyPath: "id" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const req = fn(t.objectStore(store));
    t.oncomplete = () => { db.close(); resolve(req ? req.result : undefined); };
    t.onerror = () => { db.close(); reject(t.error); };
    t.onabort = () => { db.close(); reject(t.error); };
  });
}

// ------------------------------------------------------------------ draft (wizard state)
export interface Draft {
  files: { name: string; type: string; blob: Blob }[];
  text: string;
  mode: "file" | "paste" | "sample";
  dataType?: string;
  sector?: string;
  size?: string;
  org: string;
  checks: string[];
  detection?: unknown;
  savedAt: string;
}

export async function saveDraft(d: Omit<Draft, "savedAt">): Promise<"saved" | "too-big" | "unavailable"> {
  const bytes = d.files.reduce((a, f) => a + f.blob.size, 0) + d.text.length;
  if (bytes > DRAFT_LIMIT) {
    try { await tx("draft", "readwrite", (s) => s.put({ ...d, files: [], savedAt: new Date().toISOString() }, "current")); } catch { /* ignore */ }
    return "too-big";
  }
  try {
    await tx("draft", "readwrite", (s) => s.put({ ...d, savedAt: new Date().toISOString() }, "current"));
    return "saved";
  } catch {
    return "unavailable";
  }
}

export async function loadDraft(): Promise<Draft | undefined> {
  try {
    return (await tx<Draft>("draft", "readonly", (s) => s.get("current") as IDBRequest<Draft>)) ?? undefined;
  } catch {
    return undefined;
  }
}

export async function clearDraft(): Promise<void> {
  try { await tx("draft", "readwrite", (s) => s.delete("current")); } catch { /* ignore */ }
}

// ------------------------------------------------------------------ saved reports
export interface SavedReport {
  id: string;
  savedAt: string;
  title: string;
  entityIds: string[];
  runId?: string;
  classification?: unknown;
  autoClassified?: string[];
  checks?: string[];
  data: unknown; // summary + findings + entities snapshot
  bytes: number;
}

export async function listReports(): Promise<SavedReport[]> {
  try {
    const all = (await tx<SavedReport[]>("history", "readonly", (s) => s.getAll() as IDBRequest<SavedReport[]>)) ?? [];
    return all.sort((a, b) => b.savedAt.localeCompare(a.savedAt));
  } catch {
    return [];
  }
}

export async function getReport(id: string): Promise<SavedReport | undefined> {
  try {
    return await tx<SavedReport>("history", "readonly", (s) => s.get(id) as IDBRequest<SavedReport>);
  } catch {
    return undefined;
  }
}

export async function deleteReport(id: string): Promise<void> {
  try { await tx("history", "readwrite", (s) => s.delete(id)); } catch { /* ignore */ }
}

/** Save a report; removes the oldest saved reports if the total would pass HISTORY_LIMIT. */
export async function saveReport(r: Omit<SavedReport, "id" | "savedAt" | "bytes">): Promise<SavedReport | undefined> {
  try {
    const bytes = new Blob([JSON.stringify(r.data)]).size;
    const rec: SavedReport = { ...r, id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, savedAt: new Date().toISOString(), bytes };
    const existing = (await listReports()).sort((a, b) => a.savedAt.localeCompare(b.savedAt)); // oldest first
    let total = existing.reduce((a, x) => a + x.bytes, 0) + bytes;
    for (const old of existing) {
      if (total <= HISTORY_LIMIT) break;
      await deleteReport(old.id);
      total -= old.bytes;
    }
    await tx("history", "readwrite", (s) => s.put(rec));
    return rec;
  } catch {
    return undefined;
  }
}

export const fmtBytes = (b: number) =>
  b >= 1024 ** 3 ? `${(b / 1024 ** 3).toFixed(2)} GB` : b >= 1024 ** 2 ? `${(b / 1024 ** 2).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`;
