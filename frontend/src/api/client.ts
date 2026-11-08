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

const RAW_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const API_BASE_URL = RAW_API_BASE_URL.replace(/\/+$/, '');

class ApiClient {
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${API_BASE_URL}${cleanEndpoint}`;
    const method = (options?.method || 'GET').toUpperCase();
    const headers: Record<string, string> = {};
    if (method !== 'GET' && method !== 'HEAD') {
      headers['Content-Type'] = 'application/json';
    }

    const controller = new AbortController();
    // 75-second timeout to allow sufficient window for Render free-tier cold boot
    const timeoutId = setTimeout(() => controller.abort(), 75000);

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
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `HTTP error ${response.status}`);
      }

      return await response.json();
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error?.name === 'AbortError') {
        const timeoutErr = new Error('Server took too long to respond. The cloud service may be cold-booting, please retry in a few moments.');
        console.error(`API request timeout [${endpoint}]`);
        throw timeoutErr;
      }
      console.error(`API request failed [${endpoint}]:`, error);
      throw error;
    }
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

  async uploadSource(formData: FormData): Promise<{ source: SpreadsheetSource; message: string; sync_success: boolean }> {
    const url = `${API_BASE_URL}/sources/upload`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `Upload failed with status ${response.status}`);
    }
    return await response.json();
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

  async triggerSync(source = 'active'): Promise<{ success: boolean; status: SyncStatus }> {
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
