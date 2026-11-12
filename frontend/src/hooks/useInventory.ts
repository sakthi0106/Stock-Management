import { useState, useEffect, useCallback, useRef } from 'react';
import { Product, InventoryFilters, SyncStatus } from '../types';
import { apiClient } from '../api/client';

export function useInventory(
  initialFilters?: Partial<InventoryFilters>,
  refreshKey?: string | null,
  source: string = 'active'
) {
  const [filters, setFilters] = useState<InventoryFilters>({
    search: '',
    sheet: '',
    category: '',
    partNo: '',
    uom: '',
    status: '',
    fromDate: '',
    toDate: '',
    page: 1,
    pageSize: 20,
    sortBy: 'product_id',
    sortOrder: 'asc',
    ...initialFilters,
  });

  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [categories, setCategories] = useState<string[]>([]);
  const [sheets, setSheets] = useState<string[]>([]);
  const [uoms, setUoms] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [syncing, setSyncing] = useState(false);

  // Sync external search updates
  useEffect(() => {
    if (initialFilters?.search !== undefined) {
      setFilters((prev) => (prev.search !== initialFilters.search ? { ...prev, search: initialFilters.search || '', page: 1 } : prev));
    }
  }, [initialFilters?.search]);

  // Sync external status filter updates
  useEffect(() => {
    if (initialFilters?.status !== undefined) {
      setFilters((prev) => (prev.status !== initialFilters.status ? { ...prev, status: initialFilters.status || '', page: 1 } : prev));
    }
  }, [initialFilters?.status]);

  const isFirstMount = useRef(true);

  const fetchInventory = useCallback(async (isBackground = false) => {
    if (!isBackground) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await apiClient.getInventory({ ...filters, source });
      setProducts(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setCategories(data.categories);
      setSheets(data.sheets);
      setUoms(data.uoms);
    } catch (err: any) {
      setError(err.message || 'Failed to load inventory data');
    } finally {
      setLoading(false);
    }
  }, [filters, source]);

  const fetchSyncStatus = useCallback(async () => {
    try {
      const status = await apiClient.getSyncStatus();
      setSyncStatus(status);
    } catch (err) {
      console.warn('Could not fetch sync status', err);
    }
  }, []);

  const triggerManualSync = async () => {
    setSyncing(true);
    try {
      const res = await apiClient.triggerSync(source);
      setSyncStatus(res.status);
      await fetchInventory(false);
    } catch (err: any) {
      setError(err.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  // Debounced fetch for instant responsiveness when typing search
  useEffect(() => {
    const isBackground = !isFirstMount.current && products.length > 0;
    isFirstMount.current = false;
    const handler = setTimeout(() => {
      fetchInventory(isBackground);
    }, 150);
    return () => clearTimeout(handler);
  }, [fetchInventory, refreshKey]);

  useEffect(() => {
    fetchSyncStatus();
    const interval = setInterval(fetchSyncStatus, 20000);
    return () => clearInterval(interval);
  }, [fetchSyncStatus]);

  const updateFilters = (newFilters: Partial<InventoryFilters>) => {
    setFilters((prev) => ({
      ...prev,
      ...newFilters,
      page: newFilters.page !== undefined ? newFilters.page : 1,
    }));
  };

  return {
    filters,
    setFilters: updateFilters,
    products,
    total,
    totalPages,
    categories,
    sheets,
    uoms,
    loading,
    error,
    syncStatus,
    syncing,
    triggerManualSync,
    refetch: fetchInventory,
  };
}
