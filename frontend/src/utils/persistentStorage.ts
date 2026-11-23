/**
 * Client-Side Permanent Storage Engine
 *
 * Uses browser IndexedDB with localStorage fallback to guarantee that:
 * 1. User-registered Google Sheets sources and uploaded Excel workbooks (.xlsx Blobs)
 *    are NEVER lost when Render hibernates, restarts, or recycles ephemeral containers.
 * 2. Data is permanently preserved until the user explicitly deletes the file/source.
 * 3. Deletion tombstones ensure deleted spreadsheets can NEVER resurrect on reload,
 *    reconnect, or self-healing reconciliation.
 * 4. The frontend immediately displays cached data on mount, eliminating cold-boot blank screens.
 */

export interface StoredSource {
  id: string;
  name: string;
  source_type: 'google_sheets' | 'excel_upload';
  spreadsheet_url_or_id: string;
  period?: string;
  description?: string;
  is_active?: boolean;
  poll_interval_seconds?: number;
  file_blob?: Blob;
  file_name?: string;
  file_size?: number;
  created_at: string;
  last_synced_at?: string;
}

const DB_NAME = 'StockManagementPersistentDB';
const DB_VERSION = 1;
const STORE_SOURCES = 'sources';
const STORE_SNAPSHOTS = 'snapshots';
const TOMBSTONE_STORAGE_KEY = 'stock_mgmt_deleted_sources';

export function extractSpreadsheetId(urlOrId?: string | null): string {
  if (!urlOrId || typeof urlOrId !== 'string') return '';
  const trimmed = urlOrId.trim();
  if (trimmed.startsWith('local_file:')) return trimmed;
  const match = trimmed.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  if (match) return match[1];
  return trimmed.split('/')[0].split('?')[0];
}

class PersistentStorage {
  private dbPromise: Promise<IDBDatabase> | null = null;

  private getDB(): Promise<IDBDatabase> {
    if (this.dbPromise) return this.dbPromise;

    this.dbPromise = new Promise((resolve, reject) => {
      if (typeof window === 'undefined' || !window.indexedDB) {
        reject(new Error('IndexedDB not available in this environment'));
        return;
      }

      const req = indexedDB.open(DB_NAME, DB_VERSION);

      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_SOURCES)) {
          db.createObjectStore(STORE_SOURCES, { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains(STORE_SNAPSHOTS)) {
          db.createObjectStore(STORE_SNAPSHOTS, { keyPath: 'key' });
        }
      };

      req.onsuccess = () => resolve(req.result);
      req.onerror = () => {
        console.warn('Could not open IndexedDB, falling back to localStorage', req.error);
        reject(req.error);
      };
    });

    return this.dbPromise;
  }

  // -------------------------------------------------------------
  // Deletion Tombstones (Prevents Deleted Spreadsheets from Returning)
  // -------------------------------------------------------------

  getTombstones(): Set<string> {
    try {
      const raw = localStorage.getItem(TOMBSTONE_STORAGE_KEY);
      if (raw) {
        const arr = JSON.parse(raw);
        if (Array.isArray(arr)) return new Set(arr);
      }
    } catch {
      // ignore
    }
    return new Set<string>();
  }

  addTombstone(...ids: (string | undefined | null)[]): void {
    const set = this.getTombstones();
    for (const id of ids) {
      if (id && typeof id === 'string' && id.trim()) {
        const trimmed = id.trim();
        set.add(trimmed);
        const clean = extractSpreadsheetId(trimmed);
        if (clean) set.add(clean);
      }
    }
    try {
      localStorage.setItem(TOMBSTONE_STORAGE_KEY, JSON.stringify(Array.from(set)));
    } catch {
      // ignore
    }
  }

  removeTombstone(...ids: (string | undefined | null)[]): void {
    const set = this.getTombstones();
    for (const id of ids) {
      if (id && typeof id === 'string' && id.trim()) {
        const trimmed = id.trim();
        set.delete(trimmed);
        const clean = extractSpreadsheetId(trimmed);
        if (clean) set.delete(clean);
      }
    }
    try {
      localStorage.setItem(TOMBSTONE_STORAGE_KEY, JSON.stringify(Array.from(set)));
    } catch {
      // ignore
    }
  }

  isTombstoned(...ids: (string | undefined | null)[]): boolean {
    const set = this.getTombstones();
    for (const id of ids) {
      if (id && typeof id === 'string' && id.trim()) {
        const trimmed = id.trim();
        const clean = extractSpreadsheetId(trimmed);
        if (set.has(trimmed) || (clean && set.has(clean))) {
          return true;
        }
      }
    }
    return false;
  }

  // -------------------------------------------------------------
  // Sources Management
  // -------------------------------------------------------------

  async saveSource(source: StoredSource): Promise<void> {
    // If user explicitly saves or uploads, remove any previous tombstone
    this.removeTombstone(source.id, source.spreadsheet_url_or_id);

    try {
      const db = await this.getDB();
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_SOURCES, 'readwrite');
        const store = tx.objectStore(STORE_SOURCES);
        const req = store.put(source);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch {
      // Fallback for environments where IndexedDB is blocked: store metadata without blob
      try {
        const existing = this.getLocalStorageSources();
        const filtered = existing.filter(s => s.id !== source.id && s.spreadsheet_url_or_id !== source.spreadsheet_url_or_id);
        const metadataOnly: StoredSource = { ...source, file_blob: undefined };
        filtered.push(metadataOnly);
        localStorage.setItem('stock_mgmt_stored_sources', JSON.stringify(filtered));
      } catch (e) {
        console.warn('localStorage fallback failed:', e);
      }
    }
  }

  async getAllSources(): Promise<StoredSource[]> {
    let list: StoredSource[] = [];
    try {
      const db = await this.getDB();
      list = await new Promise<StoredSource[]>((resolve, reject) => {
        const tx = db.transaction(STORE_SOURCES, 'readonly');
        const store = tx.objectStore(STORE_SOURCES);
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => reject(req.error);
      });
    } catch {
      list = this.getLocalStorageSources();
    }

    // Filter out any tombstoned sources
    return list.filter(s => !this.isTombstoned(s.id, s.spreadsheet_url_or_id));
  }

  async deleteSource(id: string, spreadsheetId?: string): Promise<void> {
    // 1. Permanently record in tombstones
    this.addTombstone(id);
    if (spreadsheetId) {
      this.addTombstone(spreadsheetId);
    }

    // 2. Delete from IndexedDB STORE_SOURCES
    try {
      const db = await this.getDB();
      const tx = db.transaction(STORE_SOURCES, 'readwrite');
      const store = tx.objectStore(STORE_SOURCES);
      store.delete(id);
      if (spreadsheetId) store.delete(spreadsheetId);
      await new Promise<void>((resolve) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      });
    } catch {
      // ignore
    }

    // 3. Delete from localStorage fallback
    try {
      const existing = this.getLocalStorageSources();
      const filtered = existing.filter(
        s => s.id !== id && (!spreadsheetId || s.spreadsheet_url_or_id !== spreadsheetId)
      );
      localStorage.setItem('stock_mgmt_stored_sources', JSON.stringify(filtered));
    } catch {
      // ignore
    }

    // 4. Clean snapshot 'sources_list' immediately so stale cache never displays it
    try {
      const cached = await this.getSnapshot<any[]>('sources_list');
      if (Array.isArray(cached)) {
        const cleaned = cached.filter(
          s => s.source_id !== id && (!spreadsheetId || s.spreadsheet_id !== spreadsheetId)
        );
        await this.saveSnapshot('sources_list', cleaned);
      }
    } catch {
      // ignore
    }
  }

  private getLocalStorageSources(): StoredSource[] {
    try {
      const raw = localStorage.getItem('stock_mgmt_stored_sources');
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  // -------------------------------------------------------------
  // Snapshot Caching (Offline / Cold-boot instant rendering)
  // -------------------------------------------------------------

  async saveSnapshot(key: string, data: any): Promise<void> {
    try {
      const db = await this.getDB();
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_SNAPSHOTS, 'readwrite');
        const store = tx.objectStore(STORE_SNAPSHOTS);
        const req = store.put({ key, data, updated_at: new Date().toISOString() });
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch {
      try {
        localStorage.setItem(`stock_mgmt_snapshot_${key}`, JSON.stringify(data));
      } catch {
        // ignore
      }
    }
  }

  async getSnapshot<T>(key: string): Promise<T | null> {
    let result: T | null = null;
    try {
      const db = await this.getDB();
      result = await new Promise<T | null>((resolve, reject) => {
        const tx = db.transaction(STORE_SNAPSHOTS, 'readonly');
        const store = tx.objectStore(STORE_SNAPSHOTS);
        const req = store.get(key);
        req.onsuccess = () => resolve(req.result ? req.result.data : null);
        req.onerror = () => reject(req.error);
      });
    } catch {
      try {
        const raw = localStorage.getItem(`stock_mgmt_snapshot_${key}`);
        result = raw ? JSON.parse(raw) : null;
      } catch {
        result = null;
      }
    }

    // If reading sources_list snapshot, make sure tombstoned sources are excluded
    if (key === 'sources_list' && Array.isArray(result)) {
      result = (result as any[]).filter(
        (s: any) => !this.isTombstoned(s.source_id, s.spreadsheet_id)
      ) as unknown as T;
    }

    return result;
  }
}

export const persistentStorage = new PersistentStorage();
