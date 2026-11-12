import React, { useState, useEffect } from 'react';
import { Search, Filter, ArrowDownRight, ArrowUpRight, Calendar } from 'lucide-react';
import { fetchApi } from '../api';

export function DailyMovements() {
  const [movements, setMovements] = useState<any[]>([]);
  const [worksheets, setWorksheets] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState<string>('');
  const [selectedType, setSelectedType] = useState<string>('');
  const [search, setSearch] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const loadMovements = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedSheet) params.append('sheet', selectedSheet);
      if (selectedType) params.append('type', selectedType);
      if (search) params.append('search', search);

      const res = await fetchApi<any>(`/api/movements?${params.toString()}`);
      setMovements(res.items || []);
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
    loadMovements();
  }, [selectedSheet, selectedType]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadMovements();
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Daily Stock Movement Registers</h1>
          <p className="text-sm text-slate-500 mt-1">
            Date-wise IN and OUT movements extracted dynamically from your Google Sheets.
          </p>
        </div>

        {/* Filter controls */}
        <div className="flex flex-wrap items-center gap-3">
          <form onSubmit={handleSearchSubmit} className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search part no, desc..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 w-48"
            />
          </form>

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

          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="text-xs bg-white border border-slate-300 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="">All Types (IN/OUT)</option>
            <option value="IN">IN (Inward)</option>
            <option value="OUT">OUT (Outward)</option>
          </select>
        </div>
      </div>

      {/* Movements Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>Total Records Found: <strong className="text-slate-900">{movements.length}</strong></span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Date</th>
                <th className="py-3 px-4">Part No</th>
                <th className="py-3 px-4">Item Description</th>
                <th className="py-3 px-4">Category</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4 text-right">IN Qty</th>
                <th className="py-3 px-4 text-right">OUT Qty</th>
                <th className="py-3 px-4">UOM</th>
                <th className="py-3 px-4">Worksheet</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {loading ? (
                <tr>
                  <td colSpan={9} className="text-center py-12 text-slate-400 animate-pulse">
                    Loading stock movements...
                  </td>
                </tr>
              ) : movements.length > 0 ? (
                movements.map((m) => (
                  <tr key={m.movement_id} className="hover:bg-slate-50 transition">
                    <td className="py-3 px-4 font-mono font-medium text-slate-900">{m.date}</td>
                    <td className="py-3 px-4 font-mono font-medium text-blue-600">{m.part_no}</td>
                    <td className="py-3 px-4 max-w-sm truncate">{m.description}</td>
                    <td className="py-3 px-4 text-slate-500">{m.category}</td>
                    <td className="py-3 px-4">
                      <span className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                        m.movement_type === 'IN' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                      }`}>
                        {m.movement_type === 'IN' ? <ArrowDownRight className="w-3 h-3" /> : <ArrowUpRight className="w-3 h-3" />}
                        <span>{m.movement_type}</span>
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-bold text-emerald-600">
                      {m.in_qty > 0 ? m.in_qty : '-'}
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-bold text-rose-600">
                      {m.out_qty > 0 ? m.out_qty : '-'}
                    </td>
                    <td className="py-3 px-4 font-medium">{m.uom}</td>
                    <td className="py-3 px-4 text-slate-500">{m.source_sheet}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={9} className="text-center py-16 text-slate-400">
                    No movements found for the selected criteria.
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
