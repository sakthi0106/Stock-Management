import React, { useEffect, useState } from 'react';
import { X, ArrowDownRight, ArrowUpRight, Calendar } from 'lucide-react';
import { Product, Movement } from '../types';
import { apiClient } from '../api/client';
import { StockBadge } from './StockBadge';

interface ProductDetailsDrawerProps {
  product: Product | null;
  onClose: () => void;
}

export const ProductDetailsDrawer: React.FC<ProductDetailsDrawerProps> = ({ product, onClose }) => {
  const [movements, setMovements] = useState<Movement[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (product) {
      setLoading(true);
      apiClient.getProduct(product.product_id)
        .then((res) => setMovements(res.movements))
        .catch((err) => console.error(err))
        .finally(() => setLoading(false));
    }
  }, [product]);

  if (!product) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-xl bg-white border-l border-slate-200 shadow-2xl flex flex-col">
          {/* Drawer Header */}
          <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50">
            <div>
              <span className="font-mono text-xs font-bold text-cyan-700 bg-cyan-50 px-2 py-0.5 rounded border border-cyan-100">
                {product.part_no && !['NA', '-', 'None', ''].includes(product.part_no) ? product.part_no : (product.product_id && !['NA', '-', 'None', ''].includes(product.product_id) ? product.product_id : `${product.source_sheet} #${product.source_row}`)}
              </span>
              <h2 className="text-lg font-bold text-slate-900 mt-1.5">
                {product.description}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Quick Metrics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider block font-semibold">Status</span>
                <div className="mt-1">
                  <StockBadge status={product.stock_status} />
                </div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider block font-semibold">Available Stock</span>
                <span className="text-base font-bold text-slate-900 mt-1 block">
                  {product.current_stock !== null ? String(product.current_stock) : '—'} <span className="text-xs font-normal text-slate-500">{product.uom}</span>
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider block font-semibold">Unit Price</span>
                <span className="text-base font-bold text-slate-900 mt-1 block">
                  {typeof product.unit_price === 'number'
                    ? `₹${product.unit_price.toFixed(2)}`
                    : product.unit_price !== null
                    ? String(product.unit_price)
                    : '—'}
                </span>
              </div>
            </div>

            {/* Product Metadata */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2.5 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Part No:</span>
                <span className="font-mono font-bold text-slate-900">{product.part_no || '—'}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Category:</span>
                <span className="text-slate-900 font-medium">{product.category}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Opening Balance (Month):</span>
                <span className="text-slate-900 font-mono font-semibold">{product.opening_stock !== null ? String(product.opening_stock) : '—'} {product.uom}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Current Stock (Latest):</span>
                <span className="text-cyan-700 font-mono font-bold">{product.current_stock !== null ? String(product.current_stock) : '—'} {product.uom}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Reorder Threshold:</span>
                <span className="text-slate-900 font-mono">{product.min_level} {product.uom}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-500">Worksheet Origin:</span>
                <span className="text-cyan-700 font-medium">{product.source_sheet} (Row {product.source_row})</span>
              </div>
            </div>

            {/* Extra Sheet Fields (Amount Strictly Excluded) */}
            {Object.keys(product.extra_fields || {}).length > 0 && (
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                  Additional Sheet Attributes
                </h4>
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2 text-xs">
                  {Object.entries(product.extra_fields).map(([k, v]) => (
                    <div key={k} className="flex justify-between py-1 border-b border-slate-200 last:border-0">
                      <span className="text-slate-500">{k}:</span>
                      <span className="text-slate-900 font-medium">{v !== null ? String(v) : '—'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Stock Movement History */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <Calendar size={14} className="text-cyan-600" />
                  <span>Daily Movements (October 2026)</span>
                </h4>
                <span className="text-xs text-slate-500">{movements.length} transactions</span>
              </div>

              {loading ? (
                <div className="py-8 text-center text-xs text-slate-500">Loading daily movements...</div>
              ) : movements.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500 border border-dashed border-slate-200 rounded-xl">
                  No inward or outward dispatches recorded for this item in October 2026.
                </div>
              ) : (
                <div className="space-y-2">
                  {movements.map((m) => {
                    const isIn = m.movement_type === 'IN';
                    return (
                      <div
                        key={m.movement_id}
                        className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs"
                      >
                        <div className="flex items-center gap-2.5">
                          <div className={`p-1.5 rounded-lg ${isIn ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
                            {isIn ? <ArrowDownRight size={14} /> : <ArrowUpRight size={14} />}
                          </div>
                          <div>
                            <div className="font-semibold text-slate-900">
                              {isIn ? `Inward (+${m.qty})` : `Outward (-${m.qty})`} {m.uom}
                            </div>
                            <div className="text-[11px] text-slate-500">
                              {m.date} {m.party_name ? `• ${m.party_name}` : ''}
                            </div>
                          </div>
                        </div>

                        {m.closing_stock !== null && (
                          <div className="text-right">
                            <span className="text-[10px] text-slate-500 block">Balance</span>
                            <span className="font-mono font-bold text-slate-800">
                              {String(m.closing_stock)}
                            </span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
