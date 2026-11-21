import {
  Product,
  Movement,
  SyncStatus,
  DashboardKPI,
  DataQualityReport,
  InventoryFilters,
  SpreadsheetSource,
  SheetInfo,
  WorksheetMetadata,
  DynamicColumn,
  DynamicRecord,
  IntelligenceDataQualityReport,
  AnalysisTaskStatus,
} from '../types';

const RAW_API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').trim().replace(/\/+$/, '');
const API_BASE_URL = RAW_API_BASE_URL.startsWith('http') && !RAW_API_BASE_URL.endsWith('/api')
  ? `${RAW_API_BASE_URL}/api`
  : RAW_API_BASE_URL;

const GAS_STORAGE_KEY = 'stock_mgmt_gas_url';

export function getAppsScriptUrl(): string {
  try {
    const stored = localStorage.getItem(GAS_STORAGE_KEY);
    if (stored && stored.trim().startsWith('http')) return stored.trim();
  } catch {}
  const envGas = (import.meta.env.VITE_APPS_SCRIPT_URL || '').trim();
  if (envGas.startsWith('http')) return envGas;
  if (RAW_API_BASE_URL.includes('script.google.com')) return RAW_API_BASE_URL;
  return '';
}

export function setAppsScriptUrl(url: string): void {
  try {
    if (!url || !url.trim()) {
      localStorage.removeItem(GAS_STORAGE_KEY);
    } else {
      localStorage.setItem(GAS_STORAGE_KEY, url.trim());
    }
  } catch {}
}

class ApiClient {
  public isAppsScriptMode(): boolean {
    return Boolean(getAppsScriptUrl());
  }

  private async requestAppsScript<T>(endpoint: string, options?: RequestInit, gasUrl?: string): Promise<T> {
    const baseUrl = gasUrl || getAppsScriptUrl();
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
    const [pathPart, queryPart] = cleanEndpoint.split('?');

    let action = 'dashboard';
    const params = new URLSearchParams(queryPart || '');

    if (pathPart === 'health') {
      action = 'health';
    } else if (pathPart === 'dashboard') {
      action = 'dashboard';
    } else if (pathPart === 'inventory') {
      action = 'inventory';
    } else if (pathPart === 'sources') {
      action = 'sources';
    } else if (pathPart.startsWith('sources/')) {
      if (pathPart.includes('/sheets')) {
        action = 'sheets';
      } else if (pathPart.includes('/sync')) {
        action = 'sync';
      } else if (pathPart.includes('/activate')) {
        return { message: 'Source activated', source_id: 'gas_master' } as unknown as T;
      } else if (pathPart.includes('/archive')) {
        return { message: 'Source archived' } as unknown as T;
      } else if (options?.method === 'DELETE') {
        return { message: 'Source deleted' } as unknown as T;
      } else {
        action = 'sources';
      }
    } else if (pathPart === 'movements') {
      action = 'movements';
    } else if (pathPart === 'sync') {
      action = 'sync';
    } else {
      action = pathPart;
    }

    params.set('action', action);

    const targetUrl = `${baseUrl}${baseUrl.includes('?') ? '&' : '?'}${params.toString()}`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000);

    try {
      const response = await fetch(targetUrl, {
        method: 'GET',
        signal: controller.signal,
        redirect: 'follow',
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Google Apps Script returned status ${response.status}`);
      }

      const json = await response.json();
      if (json.error) {
        throw new Error(json.error);
      }
      return json as T;
    } catch (err: any) {
      clearTimeout(timeoutId);
      console.error('Google Apps Script request error:', err);
      throw new Error(
        `Google Apps Script Connection Notice: ${err.message || 'Unable to fetch data'}. Ensure your Web App is deployed with 'Who has access: Anyone'.`
      );
    }
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const gasUrl = getAppsScriptUrl();
    if (gasUrl) {
      return this.requestAppsScript<T>(endpoint, options, gasUrl);
    }

    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${API_BASE_URL}${cleanEndpoint}`;
    const method = (options?.method || 'GET').toUpperCase();
    const headers: Record<string, string> = {};
    if (method !== 'GET' && method !== 'HEAD') {
      headers['Content-Type'] = 'application/json';
    }

    const isIdempotent = method === 'GET' || method === 'HEAD';
    const maxAttempts = isIdempotent ? 3 : 2;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const controller = new AbortController();
      // 90-second timeout to allow sufficient window for Render free-tier cold boot
      const timeoutId = setTimeout(() => controller.abort(), 90000);

      try {
        const response = await fetch(url, {
          ...options,
          signal: options?.signal || controller.signal,
          headers: {
            ...headers,
            ...options?.headers,
          },
        });
        clearTimeout(timeoutId);

        if (!response.ok) {
          // Retry transient Render proxy / gateway errors on 502, 503, 504
          if ([502, 503, 504].includes(response.status) && attempt < maxAttempts && !options?.signal?.aborted) {
            await new Promise((r) => setTimeout(r, attempt * 2000));
            continue;
          }
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `HTTP error ${response.status}`);
        }

        return await response.json();
      } catch (error: any) {
        clearTimeout(timeoutId);
        if (error?.name === 'AbortError') {
          if (attempt < maxAttempts && !options?.signal?.aborted) {
            await new Promise((r) => setTimeout(r, 2000));
            continue;
          }
          const timeoutErr = new Error('Server took too long to respond. The cloud service may be cold-booting, please retry in a few moments.');
          console.error(`API request timeout [${endpoint}]`);
          throw timeoutErr;
        }

        const msg = String(error?.message || '');
        const isNetworkErr =
          error instanceof TypeError ||
          /failed to fetch|networkerror|load failed/i.test(msg);

        if (isNetworkErr && attempt < maxAttempts && !options?.signal?.aborted) {
          await new Promise((r) => setTimeout(r, attempt * 2000));
          continue;
        }

        if (isNetworkErr) {
          const netErr = new Error(
            `Google Apps Script not connected. Please enter your Google Apps Script Web App URL in Spreadsheet Sources or set VITE_APPS_SCRIPT_URL in Vercel to sync your Google Sheets.`
          );
          console.error(`API network failure [${endpoint}]:`, error);
          throw netErr;
        }

        console.error(`API request failed [${endpoint}]:`, error);
        throw error;
      }
    }

    throw new Error('Request failed after retries.');
  }

  async getHealth() {
    return this.request<{ status: string; sheets_connected: boolean; mode: string; sync_state: string }>('/health');
  }

  // ------------------------------------------------------------------ //
  //  Spreadsheet Sources                                                  //
  // ------------------------------------------------------------------ //

  async getSources(includeDisabled = false): Promise<{ sources: SpreadsheetSource[]; total: number }> {
    return this.request(`/sources?include_disabled=${includeDisabled}`);
  }

  async getSource(sourceId: string): Promise<{ source: SpreadsheetSource }> {
    return this.request(`/sources/${encodeURIComponent(sourceId)}`);
  }

  async createSource(data: {
    name: string;
    spreadsheet_url_or_id: string;
    period?: string;
    description?: string;
    status?: string;
    is_active?: boolean;
    poll_interval_seconds?: number;
  }): Promise<{ source: SpreadsheetSource; message: string }> {
    return this.request('/sources', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateSource(
    sourceId: string,
    updates: Partial<SpreadsheetSource>
  ): Promise<{ source: SpreadsheetSource }> {
    return this.request(`/sources/${encodeURIComponent(sourceId)}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async uploadSource(formData: FormData): Promise<{ source: SpreadsheetSource; sources?: SpreadsheetSource[]; message: string; sync_success: boolean }> {
    const url = `${API_BASE_URL}/sources/upload`;
    for (let attempt = 1; attempt <= 3; attempt++) {
      const controller = new AbortController();
      // 120-second timeout for large multi-sheet Excel files
      const timeoutId = setTimeout(() => controller.abort(), 120000);
      try {
        const response = await fetch(url, {
          method: 'POST',
          body: formData,
          signal: controller.signal,
        });
        clearTimeout(timeoutId);
        if (!response.ok) {
          // Retry on 502/503/504 while Render is warming up
          if ([502, 503, 504].includes(response.status) && attempt < 3) {
            await new Promise((r) => setTimeout(r, attempt * 2500));
            continue;
          }
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `Upload failed with status ${response.status}`);
        }
        return await response.json();
      } catch (err: any) {
        clearTimeout(timeoutId);
        const msg = String(err?.message || '');
        const isNetworkErr = err instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(msg) || err?.name === 'AbortError';
        if (isNetworkErr && attempt < 3) {
          // If server was cold-booting on Render free tier, wait 2.5s and retry
          await new Promise((r) => setTimeout(r, attempt * 2500));
          continue;
        }
        if (isNetworkErr) {
          throw new Error(
            `Cannot connect to data source. Ensure your Google Apps Script Web App URL is configured or online.`
          );
        }
        throw err;
      }
    }
    throw new Error('Upload failed after retries.');
  }

  async deleteSourceSheet(sourceId: string, sheetName: string): Promise<{ message: string }> {
    return this.request(`/sources/${encodeURIComponent(sourceId)}/sheets/${encodeURIComponent(sheetName)}`, {
      method: 'DELETE',
    });
  }

  async deleteSource(sourceId: string): Promise<{ message: string }> {
    return this.request(`/sources/${encodeURIComponent(sourceId)}`, { method: 'DELETE' });
  }

  async activateSource(sourceId: string): Promise<{ message: string; source_id: string }> {
    return this.request(`/sources/${encodeURIComponent(sourceId)}/activate`, { method: 'POST' });
  }

  async archiveSource(sourceId: string): Promise<{ message: string }> {
    return this.request(`/sources/${encodeURIComponent(sourceId)}/archive`, { method: 'POST' });
  }

  async syncSource(sourceId: string, force = true): Promise<{ success: boolean; status: any }> {
    return this.request(`/sources/${encodeURIComponent(sourceId)}/sync`, {
      method: 'POST',
      body: JSON.stringify({ force }),
    });
  }

  async getSourceSheets(sourceId: string): Promise<{ source_id: string; sheets: SheetInfo[]; total: number }> {
    return this.request(`/sources/${encodeURIComponent(sourceId)}/sheets`);
  }

  // ------------------------------------------------------------------ //
  //  Dashboard                                                            //
  // ------------------------------------------------------------------ //

  async getDashboard(source = 'active'): Promise<DashboardKPI> {
    return this.request<DashboardKPI>(`/dashboard?source=${encodeURIComponent(source)}`);
  }

  // ------------------------------------------------------------------ //
  //  Inventory                                                            //
  // ------------------------------------------------------------------ //

  async getInventory(filters: Partial<InventoryFilters> & { source?: string }): Promise<{
    items: Product[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
    categories: string[];
    sheets: string[];
    uoms: string[];
    source_filter?: string;
  }> {
    const params = new URLSearchParams();
    if (filters.source) params.append('source', filters.source);
    if (filters.search) params.append('search', filters.search);
    if (filters.sheet) params.append('sheet', filters.sheet);
    if (filters.category) params.append('category', filters.category);
    if (filters.partNo) params.append('part_no', filters.partNo);
    if (filters.uom) params.append('uom', filters.uom);
    if (filters.status) params.append('status', filters.status);
    if (filters.page) params.append('page', filters.page.toString());
    if (filters.pageSize) params.append('page_size', filters.pageSize.toString());
    if (filters.sortBy) params.append('sort_by', filters.sortBy);
    if (filters.sortOrder) params.append('sort_order', filters.sortOrder);

    return this.request(`/inventory?${params.toString()}`);
  }

  async getProduct(productId: string, source = 'active'): Promise<{ product: Product; movements: Movement[] }> {
    return this.request(`/inventory/${encodeURIComponent(productId)}?source=${encodeURIComponent(source)}`);
  }

  // ------------------------------------------------------------------ //
  //  Movements                                                            //
  // ------------------------------------------------------------------ //

  async getMovements(filters?: {
    product_id?: string;
    from_date?: string;
    to_date?: string;
    movement_type?: string;
    source?: string;
  }): Promise<{ items: Movement[]; total: number }> {
    const params = new URLSearchParams();
    if (filters?.source) params.append('source', filters.source);
    if (filters?.product_id) params.append('product_id', filters.product_id);
    if (filters?.from_date) params.append('from_date', filters.from_date);
    if (filters?.to_date) params.append('to_date', filters.to_date);
    if (filters?.movement_type) params.append('movement_type', filters.movement_type);

    return this.request(`/movements?${params.toString()}`);
  }

  // ------------------------------------------------------------------ //
  //  Sync                                                                 //
  // ------------------------------------------------------------------ //

  async pauseSync(): Promise<{ success: boolean; message: string; status: SyncStatus }> {
    return this.request('/sync/pause', { method: 'POST' });
  }

  async resumeSync(): Promise<{ success: boolean; message: string; status: SyncStatus }> {
    return this.request('/sync/resume', { method: 'POST' });
  }

  async getSyncStatus(): Promise<SyncStatus> {
    return this.request<SyncStatus>('/sync/status');
  }

  async triggerSync(source = 'all'): Promise<{ success: boolean; status: SyncStatus }> {
    return this.request(`/sync/refresh?source=${encodeURIComponent(source)}`, { method: 'POST' });
  }

  async getSyncHistory(sourceId?: string, limit = 15): Promise<{ runs: any[]; total: number }> {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (sourceId) params.append('source', sourceId);
    return this.request(`/sync/history?${params.toString()}`);
  }

  // ------------------------------------------------------------------ //
  //  Data Quality                                                         //
  // ------------------------------------------------------------------ //

  async getDataQuality(source = 'active'): Promise<DataQualityReport> {
    return this.request<DataQualityReport>(`/data-quality?source=${encodeURIComponent(source)}`);
  }

  // ------------------------------------------------------------------ //
  //  Spreadsheet Intelligence & Universal Data Recognition             //
  // ------------------------------------------------------------------ //

  async getIntelligenceSources(): Promise<{ sources: SpreadsheetSource[]; total: number }> {
    return this.request<{ sources: SpreadsheetSource[]; total: number }>('/spreadsheet-intelligence/sources');
  }

  async triggerIntelligenceAnalysis(sourceId?: string): Promise<{ success: boolean; message: string; task_id?: string; source_id: string }> {
    return this.request<{ success: boolean; message: string; task_id?: string; source_id: string }>('/spreadsheet-intelligence/analyze', {
      method: 'POST',
      body: JSON.stringify({ source_id: sourceId }),
    });
  }

  async getIntelligenceTaskStatus(taskId: string): Promise<AnalysisTaskStatus> {
    return this.request<AnalysisTaskStatus>(`/spreadsheet-intelligence/status/${encodeURIComponent(taskId)}`);
  }

  async uploadIntelligenceSpreadsheet(formData: FormData): Promise<{ success: boolean; message: string; source_id: string; task_id?: string }> {
    const url = `${API_BASE_URL}/spreadsheet-intelligence/upload`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to upload spreadsheet');
    }
    return response.json();
  }

  async getIntelligenceWorksheets(sourceId: string): Promise<{ source_id: string; worksheets: WorksheetMetadata[]; total: number }> {
    return this.request<{ source_id: string; worksheets: WorksheetMetadata[]; total: number }>(
      `/spreadsheet-intelligence/sources/${encodeURIComponent(sourceId)}/worksheets`
    );
  }

  async getIntelligenceWorksheetDetails(
    sourceId: string,
    sheetName: string
  ): Promise<{ worksheet: WorksheetMetadata; columns: DynamicColumn[] }> {
    return this.request<{ worksheet: WorksheetMetadata; columns: DynamicColumn[] }>(
      `/spreadsheet-intelligence/sources/${encodeURIComponent(sourceId)}/worksheets/${encodeURIComponent(sheetName)}`
    );
  }

  async getIntelligenceColumns(
    sourceId: string,
    sheetName: string
  ): Promise<{ source_id: string; sheet_name: string; columns: DynamicColumn[]; total: number }> {
    return this.request<{ source_id: string; sheet_name: string; columns: DynamicColumn[]; total: number }>(
      `/spreadsheet-intelligence/sources/${encodeURIComponent(sourceId)}/worksheets/${encodeURIComponent(sheetName)}/columns`
    );
  }

  async updateIntelligenceColumns(
    sourceId: string,
    sheetName: string,
    columns: Partial<DynamicColumn>[]
  ): Promise<{ success: boolean; message: string; columns: DynamicColumn[] }> {
    return this.request<{ success: boolean; message: string; columns: DynamicColumn[] }>(
      `/spreadsheet-intelligence/sources/${encodeURIComponent(sourceId)}/worksheets/${encodeURIComponent(sheetName)}/columns`,
      {
        method: 'PUT',
        body: JSON.stringify({ columns }),
      }
    );
  }

  async getIntelligenceRecords(
    sourceId: string,
    sheetName: string,
    page = 1,
    limit = 50,
    search = ''
  ): Promise<{ records: DynamicRecord[]; total: number; page: number; limit: number; total_pages: number }> {
    const params = new URLSearchParams({
      page: String(page),
      limit: String(limit),
    });
    if (search) params.append('search', search);
    return this.request<{ records: DynamicRecord[]; total: number; page: number; limit: number; total_pages: number }>(
      `/spreadsheet-intelligence/sources/${encodeURIComponent(sourceId)}/worksheets/${encodeURIComponent(sheetName)}/records?${params.toString()}`
    );
  }

  async getIntelligenceDataQuality(sourceId: string): Promise<IntelligenceDataQualityReport> {
    return this.request<IntelligenceDataQualityReport>(
      `/spreadsheet-intelligence/sources/${encodeURIComponent(sourceId)}/data-quality`
    );
  }

  async syncApprovedIntelligenceData(sourceId: string): Promise<{ success: boolean; message: string; imported_products: number; worksheets_count: number }> {
    return this.request<{ success: boolean; message: string; imported_products: number; worksheets_count: number }>(
      `/spreadsheet-intelligence/sources/${encodeURIComponent(sourceId)}/sync`,
      {
        method: 'POST',
      }
    );
  }
}

export const apiClient = new ApiClient();
