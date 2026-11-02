import React from 'react';
import { Filter, RotateCcw } from 'lucide-react';
import { InventoryFilters } from '../types';

interface FilterBarProps {
  filters: InventoryFilters;
  onFilterChange: (newFilters: Partial<InventoryFilters>) => void;
  categories: string[];
  sheets: string[];
  uoms: string[];
}

export const FilterBar: React.FC<FilterBarProps> = ({
  filters,
  onFilterChange,
  categories,
  sheets,
  uoms,
}) => {
  const hasActiveFilters = Boolean(
    filters.sheet || filters.category || filters.uom || filters.status || filters.search
  );

  const resetFilters = () => {
    onFilterChange({
      search: '',
      sheet: '',
      category: '',
      partNo: '',
      uom: '',
      status: '',
      page: 1,
    });
  };

  return (
    <div className="glass-card p-4 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-600 mr-1">
        <Filter size={15} className="text-cyan-600" />
        <span>Filters:</span>
      </div>

      {/* Sheet Filter */}
      <select
        value={filters.sheet}
        onChange={(e) => onFilterChange({ sheet: e.target.value, page: 1 })}
        className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
      >
        <option value="">All Worksheets (6 Sheets)</option>
        {sheets.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>

      {/* Category Filter */}
      <select
        value={filters.category}
        onChange={(e) => onFilterChange({ category: e.target.value, page: 1 })}
        className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
      >
        <option value="">All Categories</option>
        {categories.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>

      {/* Stock Status Filter */}
      <select
        value={filters.status}
        onChange={(e) => onFilterChange({ status: e.target.value, page: 1 })}
        className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
      >
        <option value="">All Stock Status</option>
        <option value="In Stock">In Stock</option>
        <option value="Low Stock">Low Stock</option>
        <option value="Out of Stock">Out of Stock</option>
        <option value="Unknown">Special (NA / -)</option>
      </select>

      {/* UOM Filter */}
      <select
        value={filters.uom}
        onChange={(e) => onFilterChange({ uom: e.target.value, page: 1 })}
        className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-800 focus:bg-white focus:outline-none focus:border-cyan-500"
      >
        <option value="">All Units (UOM)</option>
        {uoms.map((u) => (
          <option key={u} value={u}>{u}</option>
        ))}
      </select>

      {/* Reset Button */}
      {hasActiveFilters && (
        <button
          onClick={resetFilters}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors"
        >
          <RotateCcw size={13} />
          <span>Reset</span>
        </button>
      )}
    </div>
  );
};
