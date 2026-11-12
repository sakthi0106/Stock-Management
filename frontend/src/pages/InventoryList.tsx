import React, { useState, useEffect } from 'react';
import { Search, Package, Layers } from 'lucide-react';
import { fetchApi } from '../api';

export function InventoryList() {
  const [items, setItems] = useState<any[]>([]);
  const [worksheets, setWorksheets] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState<string>('');
  const [search, setSearch] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const loadItems = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedSheet) params.append('sheet', selectedSheet);
      if (search) params.append('search', search);

      const res = await fetchApi<any>(`/api/inventory?${params.toString()}`);
      setItems(res.items || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApi<any>('/api/worksheets')
      .then(res => {
        const names = (res.worksheets || []).map((w: any) => w.sheet_name);
        setWorksheets(names);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    loadItems();
  }, [selectedSheet]);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Inventory Catalog</h1>
          <p className="text-sm text-slate-500 mt-1">
            Current stock quantities, balances, and catalog items from Google Sheets.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search part no, desc..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && loadItems()}
              className="pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 w-52"
            />
          </div>

          <select
            value={selectedSheet}
            onChange={(e) => setSelectedSheet(e.target.value)}
            className="text-xs bg-white border border-slate-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="">All Worksheets</option>
            {worksheets.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>Total Catalog Items: <strong className="text-slate-900">{items.length}</strong></span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Part No</th>
                <th className="py-3 px-4">Item Description</th>
                <th className="py-3 px-4">Category</th>
                <th className="py-3 px-4 text-right">Opening Stock</th>
                <th className="py-3 px-4 text-right">Total IN</th>
                <th className="py-3 px-4 text-right">Total OUT</th>
                <th className="py-3 px-4 text-right">Current Balance</th>
                <th className="py-3 px-4">UOM</th>
                <th className="py-3 px-4">Worksheet</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {loading ? (
                <tr>
                  <td colSpan={9} className="text-center py-12 text-slate-400 animate-pulse">
                    Loading inventory catalog...
                  </td>
                </tr>
              ) : items.length > 0 ? (
                items.map((p, idx) => (
                  <tr key={`${p.source_sheet}-${p.part_no}-${idx}`} className="hover:bg-slate-50 transition">
                    <td className="py-3 px-4 font-mono font-medium text-blue-600">{p.part_no}</td>
                    <td className="py-3 px-4 max-w-sm truncate">{p.description}</td>
                    <td className="py-3 px-4 text-slate-500">{p.category}</td>
                    <td className="py-3 px-4 text-right font-mono">{p.opening_stock || 0}</td>
                    <td className="py-3 px-4 text-right font-mono font-semibold text-emerald-600">{p.in_qty || 0}</td>
                    <td className="py-3 px-4 text-right font-mono font-semibold text-rose-600">{p.out_qty || 0}</td>
                    <td className="py-3 px-4 text-right font-mono font-bold text-slate-900">{p.current_stock || 0}</td>
                    <td className="py-3 px-4 font-medium">{p.uom}</td>
                    <td className="py-3 px-4 text-slate-500">{p.source_sheet}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={9} className="text-center py-16 text-slate-400">
                    No catalog items found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
