import React, { useState, useMemo } from 'react';
import { Movement } from '../types';
import { Calendar, ArrowDownRight, ArrowUpRight, Search, ChevronLeft, ChevronRight, Layers } from 'lucide-react';

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

const PAGE_SIZE = 50;

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
  const [currentPage, setCurrentPage] = useState(1);
  const [sheetFilter, setSheetFilter] = useState('');

  // Extract distinct origin sheets
  const distinctSheets = useMemo(() => {
    return Array.from(new Set(movements.map((m) => m.source_sheet).filter(Boolean))).sort();
  }, [movements]);

  // Client-side filtering for sheet and general text search across description/part_no
  const filteredMovements = useMemo(() => {
    return movements.filter((m) => {
      if (sheetFilter && m.source_sheet !== sheetFilter) return false;
      if (productFilter) {
        const q = productFilter.toLowerCase().trim();
        const pId = (m.product_id || '').toLowerCase();
        const pNo = (m.part_no || '').toLowerCase();
        const desc = (m.description || '').toLowerCase();
        const refNo = (m.reference_no || '').toLowerCase();
        const party = (m.party_name || '').toLowerCase();
        if (!pId.includes(q) && !pNo.includes(q) && !desc.includes(q) && !refNo.includes(q) && !party.includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [movements, sheetFilter, productFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredMovements.length / PAGE_SIZE));
  const paginatedMovements = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredMovements.slice(start, start + PAGE_SIZE);
  }, [filteredMovements, currentPage]);

  // Reset to page 1 on filter changes
  React.useEffect(() => {
    setCurrentPage(1);
  }, [sheetFilter, productFilter, fromDate, toDate, movementType]);

  const totalInCount = useMemo(() => movements.filter((m) => m.movement_type === 'IN').length, [movements]);
  const totalOutCount = useMemo(() => movements.filter((m) => m.movement_type === 'OUT').length, [movements]);

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
            className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500 font-medium"
          >
            <option value="">All Movements ({movements.length})</option>
            <option value="IN">Inward Receipts ({totalInCount})</option>
            <option value="OUT">Outward Dispatches ({totalOutCount})</option>
          </select>
        </div>

        {distinctSheets.length > 1 && (
          <div className="flex items-center gap-2">
            <select
              value={sheetFilter}
              onChange={(e) => setSheetFilter(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500 font-medium"
            >
              <option value="">All Worksheets ({distinctSheets.length})</option>
              {distinctSheets.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="relative ml-auto">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search Part No, Ref, Party..."
            value={productFilter}
            onChange={(e) => onProductFilterChange(e.target.value)}
            className="pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500 w-48 sm:w-64"
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
                <th className="py-3.5 px-4">Part No / Item Code</th>
                <th className="py-3.5 px-4">Description</th>
                <th className="py-3.5 px-3">Type</th>
                <th className="py-3.5 px-3">Opening</th>
                <th className="py-3.5 px-3">In Qty</th>
                <th className="py-3.5 px-3">Out Qty</th>
                <th className="py-3.5 px-3">Closing</th>
                <th className="py-3.5 px-3">UOM</th>
                <th className="py-3.5 px-3">Reference / Party</th>
                <th className="py-3.5 px-4">Worksheet</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {paginatedMovements.length === 0 ? (
                <tr>
                  <td colSpan={11} className="py-12 text-center text-slate-500">
                    <div className="space-y-1.5">
                      <p className="font-semibold text-slate-700">No stock movements found.</p>
                      <p className="text-xs text-slate-400">
                        Spreadsheet IN/OUT transactions, date registers, and receipts/dispatches will appear here when available.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                paginatedMovements.map((m) => {
                  const isIn = m.movement_type === 'IN';
                  return (
                    <tr key={m.movement_id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 font-mono font-medium text-slate-600 whitespace-nowrap">{m.date}</td>
                      <td className="py-3 px-4 font-mono font-bold text-cyan-700 whitespace-nowrap">
                        {m.part_no && m.part_no !== 'NA' ? m.part_no : m.product_id}
                      </td>
                      <td className="py-3 px-4 font-medium text-slate-900 max-w-[200px] truncate" title={m.description}>
                        {m.description || '—'}
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                            isIn
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                          }`}
                        >
                          {isIn ? <ArrowDownRight size={11} /> : <ArrowUpRight size={11} />}
                          {m.movement_type}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-mono text-slate-600">{m.opening_stock !== null ? String(m.opening_stock) : '—'}</td>
                      <td className="py-3 px-3 font-mono font-bold text-emerald-600">
                        {m.in_qty > 0 ? `+${m.in_qty}` : '—'}
                      </td>
                      <td className="py-3 px-3 font-mono font-bold text-rose-600">
                        {m.out_qty > 0 ? `-${m.out_qty}` : '—'}
                      </td>
                      <td className="py-3 px-3 font-mono font-bold text-slate-900">{m.closing_stock !== null ? String(m.closing_stock) : '—'}</td>
                      <td className="py-3 px-3 font-semibold text-slate-600">{m.uom}</td>
                      <td className="py-3 px-3 text-slate-600 max-w-[150px] truncate">
                        {m.reference_no || m.party_name ? (
                          <span title={`${m.reference_no} ${m.party_name}`.trim()}>
                            {m.reference_no && <strong className="font-mono text-slate-800">{m.reference_no}</strong>}
                            {m.reference_no && m.party_name && ' • '}
                            {m.party_name}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-600 font-medium whitespace-nowrap">
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[11px]">
                          {m.source_sheet}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {filteredMovements.length > PAGE_SIZE && (
          <div className="flex items-center justify-between p-4 bg-slate-50 border-t border-slate-200 text-xs text-slate-600">
            <div>
              Showing <strong>{(currentPage - 1) * PAGE_SIZE + 1}</strong> to{' '}
              <strong>{Math.min(currentPage * PAGE_SIZE, filteredMovements.length)}</strong> of{' '}
              <strong>{filteredMovements.length}</strong> transactions
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 transition"
              >
                <ChevronLeft size={14} />
              </button>
              <span className="px-3 py-1 font-semibold text-slate-700">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 transition"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
