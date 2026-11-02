import React, { useState, useEffect } from 'react';
import { Download, Calendar } from 'lucide-react';
import { Movement } from '../types';
import { apiClient } from '../api/client';

interface ReportsProps {
  refreshKey?: string | null;
}

export const Reports: React.FC<ReportsProps> = ({ refreshKey }) => {
  const [movements, setMovements] = useState<Movement[]>([]);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    apiClient.getMovements({ from_date: fromDate, to_date: toDate })
      .then((res) => setMovements(res.items))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [fromDate, toDate, refreshKey]);

  const exportCSV = () => {
    if (movements.length === 0) return;
    // Strictly NO Amount column in export!
    const headers = ['Date', 'Part No / Product ID', 'Description', 'Type', 'Qty', 'UOM', 'Opening Stock', 'Closing Stock', 'Sheet'];
    const rows = movements.map((m) => [
      m.date,
      m.part_no && m.part_no !== "NA" ? m.part_no : m.product_id,
      `"${(m.description || '').replace(/"/g, '""')}"`,
      m.movement_type,
      m.qty,
      m.uom,
      m.opening_stock ?? '',
      m.closing_stock ?? '',
      m.source_sheet,
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `Saravanan_Stock_Movement_Report_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Audit &amp; Movement Reports</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Verified audit trail of stock inward and outward dispatches with compliant CSV exports
          </p>
        </div>

        <button
          onClick={exportCSV}
          disabled={movements.length === 0}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold shadow-xs transition-all active:scale-95 disabled:opacity-40"
        >
          <Download size={15} />
          <span>Export Movement CSV</span>
        </button>
      </div>

      <div className="glass-card p-4 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <Calendar size={15} className="text-cyan-600" />
          <span className="text-xs font-semibold text-slate-700">Period:</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <label className="text-slate-600 font-medium">From:</label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
          />
        </div>
        <div className="flex items-center gap-2 text-xs">
          <label className="text-slate-600 font-medium">To:</label>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
          />
        </div>
      </div>

      {/* Report Summary */}
      <div className="glass-card p-6 rounded-2xl bg-white border border-slate-200 shadow-xs">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-900">
            Movement Audit Table ({movements.length} Records)
          </h3>
          <span className="text-xs text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200 font-medium">
            Amounts Strictly Excluded
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-700">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-600 border-b border-slate-200">
              <tr>
                <th className="py-3 px-3">Date</th>
                <th className="py-3 px-3">Part No / ID</th>
                <th className="py-3 px-4">Description</th>
                <th className="py-3 px-3">Type</th>
                <th className="py-3 px-3">Qty</th>
                <th className="py-3 px-3">UOM</th>
                <th className="py-3 px-3">Opening</th>
                <th className="py-3 px-3">Closing</th>
                <th className="py-3 px-4">Sheet</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {movements.map((m) => (
                <tr key={m.movement_id} className="hover:bg-slate-50/80">
                  <td className="py-2.5 px-3 font-mono font-medium text-slate-600">{m.date}</td>
                  <td className="py-2.5 px-3 font-mono font-bold text-cyan-700">{m.part_no && m.part_no !== "NA" ? m.part_no : m.product_id}</td>
                  <td className="py-2.5 px-4 text-slate-900 font-medium truncate max-w-[200px]">{m.description || '—'}</td>
                  <td className="py-2.5 px-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      m.movement_type === 'IN' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                    }`}>
                      {m.movement_type}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 font-mono font-bold text-slate-900">{String(m.qty)}</td>
                  <td className="py-2.5 px-3 text-slate-600">{m.uom}</td>
                  <td className="py-2.5 px-3 font-mono text-slate-600">{m.opening_stock ?? '—'}</td>
                  <td className="py-2.5 px-3 font-mono font-bold text-slate-900">{m.closing_stock ?? '—'}</td>
                  <td className="py-2.5 px-4 text-slate-600">{m.source_sheet}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
