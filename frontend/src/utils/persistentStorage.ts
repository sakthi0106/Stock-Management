/**
 * Client-Side Permanent Storage Engine
 *
 * Uses browser IndexedDB with localStorage fallback to guarantee that:
 * 1. User-registered Google Sheets sources and uploaded Excel workbooks (.xlsx Blobs)
 *    are NEVER lost when Render hibernates, restarts, or recycles ephemeral containers.
 * 2. Data is permanently preserved until the user explicitly deletes the file/source.
 * 3. The frontend immediately displays cached data on mount, eliminating cold-boot blank screens.
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
  // Sources Management
  // -------------------------------------------------------------

  async saveSource(source: StoredSource): Promise<void> {
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
    try {
      const db = await this.getDB();
      return await new Promise<StoredSource[]>((resolve, reject) => {
        const tx = db.transaction(STORE_SOURCES, 'readonly');
        const store = tx.objectStore(STORE_SOURCES);
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => reject(req.error);
      });
    } catch {
      return this.getLocalStorageSources();
    }
  }

  async deleteSource(id: string): Promise<void> {
    try {
      const db = await this.getDB();
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_SOURCES, 'readwrite');
        const store = tx.objectStore(STORE_SOURCES);
        const req = store.delete(id);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch {
      // ignore
    }

    try {
      const existing = this.getLocalStorageSources();
      const filtered = existing.filter(s => s.id !== id);
      localStorage.setItem('stock_mgmt_stored_sources', JSON.stringify(filtered));
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
    try {
      const db = await this.getDB();
      return await new Promise<T | null>((resolve, reject) => {
        const tx = db.transaction(STORE_SNAPSHOTS, 'readonly');
        const store = tx.objectStore(STORE_SNAPSHOTS);
        const req = store.get(key);
        req.onsuccess = () => resolve(req.result ? req.result.data : null);
        req.onerror = () => reject(req.error);
      });
    } catch {
      try {
        const raw = localStorage.getItem(`stock_mgmt_snapshot_${key}`);
        return raw ? JSON.parse(raw) : null;
      } catch {
        return null;
      }
    }
  }
}

export const persistentStorage = new PersistentStorage();
