import React from 'react';
import { Product } from '../types';
import { StockBadge } from './StockBadge';
import { StockGauge } from './StockGauge';
import { Tag, Layers } from 'lucide-react';

interface InventoryCardProps {
  product: Product;
  onSelect: (product: Product) => void;
}

export const InventoryCard: React.FC<InventoryCardProps> = ({ product, onSelect }) => {
  return (
    <div
      onClick={() => onSelect(product)}
      className="glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col justify-between cursor-pointer group hover:border-cyan-300 hover:shadow-md transition-all"
    >
      <div>
        <div className="flex items-start justify-between gap-2 mb-2.5">
          <span className="font-mono text-xs font-bold text-cyan-700 bg-cyan-50 px-2 py-0.5 rounded border border-cyan-100">
            {product.part_no && product.part_no !== "NA" ? product.part_no : product.product_id}
          </span>
          <StockBadge status={product.stock_status} />
        </div>

        <h3 className="font-semibold text-slate-900 text-sm line-clamp-2 group-hover:text-cyan-700 transition-colors">
          {product.description}
        </h3>

        <div className="mt-3 flex items-center gap-3 text-xs text-slate-500">
          <div className="flex items-center gap-1">
            <Tag size={12} className="text-slate-400" />
            <span>{product.source_sheet}</span>
          </div>
          <div className="flex items-center gap-1">
            <Layers size={12} className="text-slate-400" />
            <span>{product.category}</span>
          </div>
        </div>
      </div>

      <div className="mt-5 pt-3.5 border-t border-slate-100 flex items-end justify-between">
        <div>
          <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Unit Price</span>
          <span className="text-sm font-bold text-slate-900">
            {product.unit_price === 'NA' || product.unit_price === '-'
              ? String(product.unit_price)
              : typeof product.unit_price === 'number'
              ? `₹${product.unit_price.toFixed(2)}`
              : '—'}
          </span>
        </div>
        <div>
          <StockGauge currentStock={product.current_stock} minLevel={product.min_level} uom={product.uom} />
        </div>
      </div>
    </div>
  );
};
