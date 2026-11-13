import React from 'react';
import { Product } from '../types';
import { StockBadge } from './StockBadge';
import { StockGauge } from './StockGauge';
import { ChevronUp, ChevronDown, Eye } from 'lucide-react';

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

  return (
    <div className="space-y-2">
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
                <th className="py-3.5 px-3 cursor-pointer hover:text-slate-900" onClick={() => onSort('opening_stock')}>
                  <div className="flex items-center gap-1.5">
                    Opening Stock {renderSortIcon('opening_stock')}
                  </div>
                </th>
                <th className="py-3.5 px-4 cursor-pointer hover:text-slate-900" onClick={() => onSort('current_stock')}>
                  <div className="flex items-center gap-1.5">
                    Current Stock (Latest) {renderSortIcon('current_stock')}
                  </div>
                </th>
                <th className="py-3.5 px-4 text-center">Status</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-500">
                    <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-cyan-600 border-t-transparent mr-2" />
                    Loading inventory data...
                  </td>
                </tr>
              ) : products.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-500">
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
                    <td className="py-3.5 px-3 font-mono text-xs text-slate-700 font-semibold">
                      {p.opening_stock !== null && p.opening_stock !== undefined ? String(p.opening_stock) : '—'}
                    </td>
                    <td className="py-3.5 px-4">
                      <StockGauge currentStock={p.current_stock} minLevel={p.min_level} uom={p.uom} />
                    </td>
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
