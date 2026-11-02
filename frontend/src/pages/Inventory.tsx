import React, { useState } from 'react';
import { useInventory } from '../hooks/useInventory';
import { FilterBar } from '../components/FilterBar';
import { InventoryTable } from '../components/InventoryTable';
import { InventoryCard } from '../components/InventoryCard';
import { ProductDetailsDrawer } from '../components/ProductDetailsDrawer';
import { Product } from '../types';
import { Table, LayoutGrid, ChevronLeft, ChevronRight } from 'lucide-react';
import { SourceSelector } from '../components/SourceSelector';

interface InventoryPageProps {
  initialStatusFilter?: string;
  globalSearch?: string;
  refreshKey?: string | null;
  selectedSource?: string;
  onSourceChange?: (source: string) => void;
}

export const Inventory: React.FC<InventoryPageProps> = ({
  initialStatusFilter,
  globalSearch,
  refreshKey,
  selectedSource = 'active',
  onSourceChange,
}) => {
  const [viewMode, setViewMode] = useState<'table' | 'cards'>('table');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);

  const {
    filters,
    setFilters,
    products,
    total,
    totalPages,
    categories,
    sheets,
    uoms,
    loading,
  } = useInventory({
    status: initialStatusFilter || '',
    search: globalSearch || '',
  }, refreshKey, selectedSource);

  return (
    <div className="space-y-5">
      {/* Top Header & View Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Stock Master Register</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Showing {products.length} of {total} products across all 6 worksheets
          </p>
        </div>

        {/* Source Selector & View Toggle */}
        <div className="flex flex-wrap items-center gap-3">
          {onSourceChange && (
            <SourceSelector
              value={selectedSource}
              onChange={onSourceChange}
            />
          )}

          <div className="flex items-center gap-1 bg-white p-1 rounded-xl border border-slate-200 shadow-xs">
            <button
              onClick={() => setViewMode('table')}
              className={`p-1.5 rounded-lg text-xs flex items-center gap-1.5 transition-all ${
                viewMode === 'table' ? 'bg-cyan-600 text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Table size={15} />
              <span className="hidden sm:inline">Table View</span>
            </button>
            <button
              onClick={() => setViewMode('cards')}
              className={`p-1.5 rounded-lg text-xs flex items-center gap-1.5 transition-all ${
                viewMode === 'cards' ? 'bg-cyan-600 text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <LayoutGrid size={15} />
              <span className="hidden sm:inline">Card Grid</span>
            </button>
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <FilterBar
        filters={filters}
        onFilterChange={setFilters}
        categories={categories}
        sheets={sheets}
        uoms={uoms}
      />

      {/* Content: Table or Cards */}
      {viewMode === 'table' ? (
        <InventoryTable
          products={products}
          sortBy={filters.sortBy}
          sortOrder={filters.sortOrder}
          onSort={(col) => {
            const isSameCol = filters.sortBy === col;
            setFilters({
              sortBy: col,
              sortOrder: isSameCol && filters.sortOrder === 'asc' ? 'desc' : 'asc',
            });
          }}
          onSelectProduct={(p) => setSelectedProduct(p)}
          loading={loading}
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {products.map((p) => (
            <InventoryCard
              key={`${p.source_sheet}-${p.product_id}`}
              product={p}
              onSelect={(prod) => setSelectedProduct(prod)}
            />
          ))}
        </div>
      )}

      {/* Pagination Bar */}
      <div className="glass-card px-4 py-3 rounded-2xl bg-white border border-slate-200 shadow-xs flex items-center justify-between text-xs text-slate-600">
        <div>
          Page <strong className="text-slate-900">{filters.page}</strong> of <strong className="text-slate-900">{totalPages}</strong> ({total} total products)
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setFilters({ page: Math.max(1, filters.page - 1) })}
            disabled={filters.page <= 1 || loading}
            className="p-1.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-40 disabled:pointer-events-none transition-all"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            onClick={() => setFilters({ page: Math.min(totalPages, filters.page + 1) })}
            disabled={filters.page >= totalPages || loading}
            className="p-1.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-40 disabled:pointer-events-none transition-all"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* Product Details Drawer */}
      <ProductDetailsDrawer
        product={selectedProduct}
        onClose={() => setSelectedProduct(null)}
      />
    </div>
  );
};
