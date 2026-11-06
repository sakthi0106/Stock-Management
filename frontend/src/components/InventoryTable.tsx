import React, { useState, useMemo } from 'react';
import { Product } from '../types';
import { StockBadge } from './StockBadge';
import { StockGauge } from './StockGauge';
import { ChevronUp, ChevronDown, Eye, SlidersHorizontal, Check } from 'lucide-react';

interface InventoryTableProps {
  products: Product[];
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  onSort: (column: string) => void;
  onSelectProduct: (product: Product) => void;
  loading: boolean;
}

export const InventoryTable: React.FC<InventoryTableProps> = ({
  products,
  sortBy,
  sortOrder,
  onSort,
  onSelectProduct,
  loading,
}) => {
  // Dynamically discover all custom / newly added columns from spreadsheet extra_fields
  const dynamicColKeys = useMemo(() => {
    const coreNames = [
      'part no', 'part_no', 'description', 'category', 'uom', 'unit price',
      'unit_price', 'opening stock', 'opening_stock', 'current stock',
      'closing stock', 'si no', 'sl no', 'product id', 'product_id'
    ];
    const keys = new Set<string>();
    const forbidden = [
      'amount', 'closing value', 'closing stk val', 'total price',
      'column_', 'column ', 'in', 'out', 'closing stk', 'closing stock',
      'opening stock', 'si no', 'sl no', 'sino', 'slno', 'unnamed'
    ];
    products.forEach((p) => {
      if (p.extra_fields) {
        Object.keys(p.extra_fields).forEach((k) => {
          const lk = k.toLowerCase().trim();
          if (
            !coreNames.some((c) => lk === c || lk.includes(c)) &&
            !forbidden.some((f) => lk === f || lk.startsWith(f) || lk.includes(f))
          ) {
            keys.add(k);
          }
        });
      }
    });
    return Array.from(keys);
  }, [products]);

  // Selected dynamic columns to display (defaults to first 3 if available)
  const [selectedCols, setSelectedCols] = useState<string[]>([]);
  const [isColumnPickerOpen, setIsColumnPickerOpen] = useState(false);

  // Clean up selected columns if they are no longer in dynamicColKeys
  React.useEffect(() => {
    setSelectedCols((prev) => prev.filter((c) => dynamicColKeys.includes(c)));
  }, [dynamicColKeys]);

  const toggleCol = (col: string) => {
    setSelectedCols((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]
    );
  };

  const renderSortIcon = (column: string) => {
    if (sortBy !== column) return null;
    return sortOrder === 'asc' ? <ChevronUp size={14} className="text-cyan-600" /> : <ChevronDown size={14} className="text-cyan-600" />;
  };

  const formatUnitPrice = (price: any) => {
    if (price === 'NA' || price === '-') {
      return <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 font-semibold">{price}</span>;
    }
    if (typeof price === 'number') {
      return <span className="font-semibold text-slate-900">₹{price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>;
    }
    return <span className="text-slate-400">—</span>;
  };

  const totalColSpan = 9 + selectedCols.length;

  return (
    <div className="space-y-2">
      {/* Dynamic Column Selector Bar */}
      {dynamicColKeys.length > 0 && (
        <div className="flex items-center justify-between px-2 py-1">
          <div className="text-xs text-slate-500 flex items-center gap-1.5">
            <span className="font-semibold text-slate-700">Dynamic Columns Detected:</span>
            <span>{dynamicColKeys.length} spreadsheet attribute{dynamicColKeys.length > 1 ? 's' : ''} available</span>
          </div>

          <div className="relative">
            <button
              onClick={() => setIsColumnPickerOpen(!isColumnPickerOpen)}
              className="px-2.5 py-1 text-xs font-semibold bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-lg shadow-2xs flex items-center gap-1.5 transition-all"
            >
              <SlidersHorizontal size={13} className="text-cyan-600" />
              <span>Visible Columns ({selectedCols.length})</span>
            </button>

            {isColumnPickerOpen && (
              <>
                <div
                  className="fixed inset-0 z-30"
                  onClick={() => setIsColumnPickerOpen(false)}
                />
                <div className="absolute right-0 top-8 z-40 w-64 bg-white rounded-xl border border-slate-200 shadow-xl p-2.5 space-y-1 text-xs">
                  <div className="font-bold text-slate-700 px-2 py-1 border-b border-slate-100 flex items-center justify-between">
                    <span>Spreadsheet Columns</span>
                    <button
                      onClick={() => setSelectedCols(dynamicColKeys)}
                      className="text-[10px] text-cyan-600 hover:underline font-normal"
                    >
                      Select All
                    </button>
                  </div>
                  <div className="max-h-56 overflow-y-auto space-y-0.5 pt-1">
                    {dynamicColKeys.map((col) => {
                      const isSelected = selectedCols.includes(col);
                      return (
                        <button
                          key={col}
                          onClick={() => toggleCol(col)}
                          className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-slate-50 flex items-center justify-between text-slate-700"
                        >
                          <span className="truncate max-w-[180px]">{col}</span>
                          <span className={`w-4 h-4 rounded flex items-center justify-center border ${isSelected ? 'bg-cyan-600 border-cyan-600 text-white' : 'border-slate-300'}`}>
                            {isSelected && <Check size={11} />}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Main Table */}
      <div className="glass-card bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-600 border-b border-slate-200 select-none">
              <tr>
                <th className="py-3.5 px-4 cursor-pointer hover:text-slate-900" onClick={() => onSort('product_id')}>
                  <div className="flex items-center gap-1.5">
                    Part No / ID {renderSortIcon('product_id')}
                  </div>
                </th>
                <th className="py-3.5 px-4 cursor-pointer hover:text-slate-900" onClick={() => onSort('description')}>
                  <div className="flex items-center gap-1.5">
                    Description {renderSortIcon('description')}
                  </div>
                </th>
                <th className="py-3.5 px-4 cursor-pointer hover:text-slate-900" onClick={() => onSort('category')}>
                  <div className="flex items-center gap-1.5">
                    Category {renderSortIcon('category')}
                  </div>
                </th>
                <th className="py-3.5 px-3">UOM</th>
                <th className="py-3.5 px-4 cursor-pointer hover:text-slate-900" onClick={() => onSort('unit_price')}>
                  <div className="flex items-center gap-1.5">
                    Unit Price {renderSortIcon('unit_price')}
                  </div>
                </th>
                <th className="py-3.5 px-3 text-slate-500 font-medium">Month Open</th>
                <th className="py-3.5 px-4">Current Stock (Latest)</th>

                {/* Newly Added / Dynamic Columns from Spreadsheet */}
                {selectedCols.map((colKey) => (
                  <th key={colKey} className="py-3.5 px-4 bg-cyan-50/50 text-cyan-900 border-l border-cyan-100">
                    <div className="flex flex-col">
                      <span className="font-bold">{colKey}</span>
                      <span className="text-[9px] text-cyan-600 font-normal lowercase tracking-normal">Spreadsheet</span>
                    </div>
                  </th>
                ))}

                <th className="py-3.5 px-4 text-center">Status</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={totalColSpan} className="py-12 text-center text-slate-500">
                    <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-cyan-600 border-t-transparent mr-2" />
                    Loading inventory data...
                  </td>
                </tr>
              ) : products.length === 0 ? (
                <tr>
                  <td colSpan={totalColSpan} className="py-12 text-center text-slate-500">
                    No stock items found matching your current filter criteria.
                  </td>
                </tr>
              ) : (
                products.map((p) => (
                  <tr
                    key={`${p.source_sheet}-${p.product_id}-${p.source_row}`}
                    onClick={() => onSelectProduct(p)}
                    className="hover:bg-slate-50/80 transition-colors cursor-pointer group"
                  >
                    <td className="py-3.5 px-4 font-mono font-bold text-cyan-700 text-xs">
                      <div>{p.part_no && !['NA', '-', 'None', ''].includes(p.part_no) ? p.part_no : (p.product_id && !['NA', '-', 'None', ''].includes(p.product_id) ? p.product_id : `${p.source_sheet} #${p.source_row}`)}</div>
                      <div className="text-[10px] font-normal text-slate-400 mt-0.5">{p.source_sheet}</div>
                    </td>
                    <td className="py-3.5 px-4 font-medium text-slate-900 max-w-[280px] truncate" title={p.description}>
                      {p.description}
                    </td>
                    <td className="py-3.5 px-4 text-xs text-slate-600">
                      <span className="px-2 py-0.5 rounded-md bg-slate-100 border border-slate-200">
                        {p.category}
                      </span>
                    </td>
                    <td className="py-3.5 px-3 font-semibold text-xs text-slate-700">
                      {p.uom}
                    </td>
                    <td className="py-3.5 px-4 text-xs">
                      {formatUnitPrice(p.unit_price)}
                    </td>
                    <td className="py-3.5 px-3 font-mono text-xs text-slate-500">
                      {p.opening_stock !== null ? String(p.opening_stock) : '—'}
                    </td>
                    <td className="py-3.5 px-4">
                      <StockGauge currentStock={p.current_stock} minLevel={p.min_level} uom={p.uom} />
                    </td>

                    {/* Dynamic Column Values */}
                    {selectedCols.map((colKey) => {
                      const val = p.extra_fields?.[colKey];
                      const isLit = val === 'NA' || val === 'N/A' || val === '-';
                      return (
                        <td key={colKey} className="py-3.5 px-4 text-xs border-l border-cyan-50 bg-cyan-50/20">
                          {isLit ? (
                            <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 font-semibold">{val}</span>
                          ) : val !== undefined && val !== null && val !== '' ? (
                            <span className="text-slate-800 font-medium">{String(val)}</span>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                      );
                    })}

                    <td className="py-3.5 px-4 text-center">
                      <StockBadge status={p.stock_status} />
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectProduct(p);
                        }}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-600 hover:bg-cyan-50 transition-colors"
                        title="View Details"
                      >
                        <Eye size={16} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
