import React from 'react';
import { Movement } from '../types';
import { Calendar, ArrowDownRight, ArrowUpRight, Search } from 'lucide-react';

interface DateMovementPanelProps {
  movements: Movement[];
  fromDate: string;
  toDate: string;
  onFromDateChange: (d: string) => void;
  onToDateChange: (d: string) => void;
  productFilter: string;
  onProductFilterChange: (p: string) => void;
  movementType: string;
  onMovementTypeChange: (t: string) => void;
}

export const DateMovementPanel: React.FC<DateMovementPanelProps> = ({
  movements,
  fromDate,
  toDate,
  onFromDateChange,
  onToDateChange,
  productFilter,
  onProductFilterChange,
  movementType,
  onMovementTypeChange,
}) => {
  return (
    <div className="space-y-4">
      {/* Filters Toolbar */}
      <div className="glass-card p-4 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-600 mr-2">
          <Calendar size={15} className="text-cyan-600" />
          <span>Movement Filters:</span>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-600 font-medium">From:</label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => onFromDateChange(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
          />
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-600 font-medium">To:</label>
          <input
            type="date"
            value={toDate}
            onChange={(e) => onToDateChange(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
          />
        </div>

        <div className="flex items-center gap-2">
          <select
            value={movementType}
            onChange={(e) => onMovementTypeChange(e.target.value)}
            className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
          >
            <option value="">All Movements (IN & OUT)</option>
            <option value="IN">Inward Only (Receipts)</option>
            <option value="OUT">Outward Only (Dispatches)</option>
          </select>
        </div>

        <div className="relative ml-auto">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search Part No / ID..."
            value={productFilter}
            onChange={(e) => onProductFilterChange(e.target.value)}
            className="pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
          />
        </div>
      </div>

      {/* Movements Table */}
      <div className="glass-card bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-600 border-b border-slate-200">
              <tr>
                <th className="py-3.5 px-4">Date</th>
                <th className="py-3.5 px-4">Part No / ID</th>
                <th className="py-3.5 px-4">Description</th>
                <th className="py-3.5 px-3">Type</th>
                <th className="py-3.5 px-3">Opening</th>
                <th className="py-3.5 px-3">In Qty</th>
                <th className="py-3.5 px-3">Out Qty</th>
                <th className="py-3.5 px-3">Closing</th>
                <th className="py-3.5 px-3">UOM</th>
                <th className="py-3.5 px-4">Origin Sheet</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {movements.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-12 text-center text-slate-500">
                    No movement records found for the selected period.
                  </td>
                </tr>
              ) : (
                movements.map((m) => {
                  const isIn = m.movement_type === 'IN';
                  return (
                    <tr key={m.movement_id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 font-mono font-medium text-slate-600">{m.date}</td>
                      <td className="py-3 px-4 font-mono font-bold text-cyan-700">{m.part_no && m.part_no !== "NA" ? m.part_no : m.product_id}</td>
                      <td className="py-3 px-4 font-medium text-slate-900 max-w-[220px] truncate" title={m.description}>
                        {m.description || '—'}
                      </td>
                      <td className="py-3 px-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                          isIn ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                        }`}>
                          {isIn ? <ArrowDownRight size={11} /> : <ArrowUpRight size={11} />}
                          {m.movement_type}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-mono text-slate-600">{m.opening_stock !== null ? String(m.opening_stock) : '—'}</td>
                      <td className="py-3 px-3 font-mono font-bold text-emerald-600">{m.in_qty > 0 ? `+${m.in_qty}` : '—'}</td>
                      <td className="py-3 px-3 font-mono font-bold text-rose-600">{m.out_qty > 0 ? `-${m.out_qty}` : '—'}</td>
                      <td className="py-3 px-3 font-mono font-bold text-slate-900">{m.closing_stock !== null ? String(m.closing_stock) : '—'}</td>
                      <td className="py-3 px-3 font-semibold text-slate-600">{m.uom}</td>
                      <td className="py-3 px-4 text-slate-600 font-medium">
                        {m.source_sheet}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
