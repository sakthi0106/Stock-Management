import React, { useEffect, useState } from 'react';
import { StatCard } from '../components/StatCard';
import { DashboardCharts } from './DashboardCharts';
import { DashboardKPI } from '../types';
import { apiClient } from '../api/client';
import { Package, AlertTriangle, XCircle, ArrowLeftRight, Clock, Layers } from 'lucide-react';
import { SourceSelector } from '../components/SourceSelector';

interface DashboardProps {
  onNavigateToInventory: (statusFilter?: string) => void;
  onNavigateToMovements?: () => void;
  refreshKey?: string | null;
  selectedSource?: string;
  onSourceChange?: (source: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({
  onNavigateToInventory,
  onNavigateToMovements,
  refreshKey,
  selectedSource = 'active',
  onSourceChange,
}) => {
  const [data, setData] = useState<DashboardKPI | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [retryCountdown, setRetryCountdown] = useState<number | null>(null);

  const fetchDashboard = () => {
    setLoading(true);
    setFetchError(null);
    setRetryCountdown(null);
    apiClient.getDashboard(selectedSource)
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        console.error('Failed to load dashboard:', err);
        setFetchError(err.message || 'Unable to connect to inventory backend server.');
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchDashboard();
  }, [refreshKey, selectedSource]);

  useEffect(() => {
    if (fetchError && !data) {
      setRetryCountdown(5);
      const timer = setInterval(() => {
        setRetryCountdown((prev) => {
          if (prev === null || prev <= 1) {
            clearInterval(timer);
            fetchDashboard();
            return null;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearInterval(timer);
    } else {
      setRetryCountdown(null);
    }
  }, [fetchError, data]);

  if (fetchError && !data) {
    return (
      <div className="p-8 bg-rose-50 border border-rose-200 rounded-2xl text-center space-y-4">
        <div className="inline-flex p-3 bg-rose-100 text-rose-700 rounded-full">
          <AlertTriangle size={28} />
        </div>
        <h3 className="text-lg font-bold text-rose-900">Failed to Load Inventory Dashboard</h3>
        <p className="text-sm text-rose-600 max-w-md mx-auto">{fetchError}</p>
        <button
          onClick={fetchDashboard}
          className="px-5 py-2.5 bg-rose-600 text-white rounded-xl text-sm font-semibold hover:bg-rose-700 shadow-sm transition active:scale-95"
        >
          {retryCountdown !== null ? `Retrying in ${retryCountdown}s...` : 'Retry Loading'}
        </button>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div className="bg-cyan-50/80 border border-cyan-200 p-4 rounded-2xl flex items-center gap-3 text-cyan-900 shadow-xs">
          <div className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-cyan-600 border-t-transparent shrink-0" />
          <div>
            <p className="text-sm font-semibold">Connecting to Inventory Backend...</p>
            <p className="text-xs text-cyan-700">Loading live spreadsheet inventory and warehouse metrics.</p>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-2xl bg-white border border-slate-200 animate-pulse" />
          ))}
        </div>
        <div className="h-24 rounded-2xl bg-white border border-slate-200 animate-pulse" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 h-80 rounded-2xl bg-white border border-slate-200 animate-pulse" />
          <div className="h-80 rounded-2xl bg-white border border-slate-200 animate-pulse" />
        </div>
      </div>
    );
  }

  const lastSyncFormatted = data.last_updated
    ? new Date(data.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : 'Live';

  return (
    <div className="space-y-6">
      {/* Header bar with Source Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
        <div>
          <h1 className="text-lg font-bold text-slate-800">Operational Overview</h1>
          <p className="text-xs text-slate-500">Live multi-spreadsheet stock levels, turnover, and warehouse movements</p>
        </div>
        {onSourceChange && (
          <SourceSelector
            value={selectedSource}
            onChange={onSourceChange}
          />
        )}
      </div>

      {data.total_products === 0 && (
        <div className="p-6 bg-slate-50 border border-dashed border-slate-300 rounded-2xl text-center space-y-2">
          <p className="text-sm font-semibold text-slate-800">
            No spreadsheet uploaded or connected. Please upload or register a spreadsheet to get started.
          </p>
        </div>
      )}

      {/* 4 Top KPI Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="cursor-pointer" onClick={() => onNavigateToInventory()}>
          <StatCard
            title="Total Catalog Items"
            value={data.total_products}
            subtitle="In active spreadsheet"
            icon={Package}
            variant="cyan"
          />
        </div>
        <div className="cursor-pointer" onClick={() => onNavigateToInventory('Low Stock')}>
          <StatCard
            title="Low Stock Alerts"
            value={data.low_stock_count}
            subtitle="At or below reorder threshold"
            icon={AlertTriangle}
            variant="amber"
          />
        </div>
        <div className="cursor-pointer" onClick={() => onNavigateToInventory('Out of Stock')}>
          <StatCard
            title="Out of Stock Items"
            value={data.out_of_stock_count}
            subtitle="Replenishment required"
            icon={XCircle}
            variant="rose"
          />
        </div>
        <div className="cursor-pointer" onClick={onNavigateToMovements}>
          <StatCard
            title="Daily Stock Movements"
            value={data.total_movements_count || 0}
            subtitle="Active daily Inward & Outward logs"
            icon={ArrowLeftRight}
            variant="emerald"
          />
        </div>
      </div>

      {/* Stock Quantities by UOM (Strict Separation — Rule 9) */}
      <div className="glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-cyan-600" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
              Current Available Stock by Unit of Measure (UOM Isolated)
            </h3>
          </div>
          <span className="text-[11px] text-slate-500 font-medium">
            Strict UOM Isolation (Meters, Kgs, Nos, Lengths never summed together)
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-3">
          {Object.entries(data.uom_quantities).map(([uom, qty]) => {
            if (uom === 'NA' && qty === 0) return null;
            return (
              <div key={uom} className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-center hover:bg-slate-100/60 transition-colors">
                <span className="text-[10px] text-slate-500 uppercase font-bold block">{uom}</span>
                <span className="text-lg font-bold text-slate-900 mt-0.5 block">
                  {qty.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Analytical Charts & Movement Velocity */}
      <DashboardCharts
        data={data}
        onNavigateToMovements={onNavigateToMovements}
      />
    </div>
  );
};
