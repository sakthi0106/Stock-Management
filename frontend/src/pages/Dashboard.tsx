import React, { useState, useEffect } from 'react';
import { Package, ArrowDownRight, ArrowUpRight, Activity, TrendingUp, Layers } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { fetchApi } from '../api';

export function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchApi<any>('/api/dashboard')
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[50vh]">
        <div className="text-slate-500 animate-pulse text-sm">Loading dashboard metrics...</div>
      </div>
    );
  }

  const summary = data || {
    total_items: 0,
    total_movements: 0,
    total_in_qty: 0,
    total_out_qty: 0,
    daily_trends: [],
    recent_movements: []
  };

  return (
    <div className="p-8 space-x-0 space-y-8 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Stock Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">
          Real-time metrics calculated directly from synchronized Google Sheets data.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Items</span>
            <span className="p-2 bg-blue-50 text-blue-600 rounded-lg"><Package className="w-5 h-5" /></span>
          </div>
          <div className="mt-3 text-3xl font-bold text-slate-900">{summary.total_items}</div>
          <div className="text-xs text-slate-500 mt-1">Unique catalog parts</div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total IN Quantity</span>
            <span className="p-2 bg-emerald-50 text-emerald-600 rounded-lg"><ArrowDownRight className="w-5 h-5" /></span>
          </div>
          <div className="mt-3 text-3xl font-bold text-emerald-600">{summary.total_in_qty.toLocaleString()}</div>
          <div className="text-xs text-slate-500 mt-1">Cumulative stock inwards</div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total OUT Quantity</span>
            <span className="p-2 bg-rose-50 text-rose-600 rounded-lg"><ArrowUpRight className="w-5 h-5" /></span>
          </div>
          <div className="mt-3 text-3xl font-bold text-rose-600">{summary.total_out_qty.toLocaleString()}</div>
          <div className="text-xs text-slate-500 mt-1">Cumulative stock outwards</div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Movements</span>
            <span className="p-2 bg-purple-50 text-purple-600 rounded-lg"><Activity className="w-5 h-5" /></span>
          </div>
          <div className="mt-3 text-3xl font-bold text-slate-900">{summary.total_movements}</div>
          <div className="text-xs text-slate-500 mt-1">Daily recorded transactions</div>
        </div>
      </div>

      {/* Daily Trends Chart */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Stock Velocity & Movement Trends</h2>
            <p className="text-xs text-slate-500 mt-0.5">Daily IN (Inward) vs OUT (Outward) quantities</p>
          </div>
        </div>

        {summary.daily_trends.length > 0 ? (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.daily_trends}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} />
                <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
                <Tooltip />
                <Bar dataKey="in_qty" name="IN Quantity" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="out_qty" name="OUT Quantity" fill="#f43f5e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-48 flex items-center justify-center text-slate-400 text-sm">
            No daily movements recorded yet. Connect a Google Sheet with date columns.
          </div>
        )}
      </div>

      {/* Recent Movements Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-900">Recent Stock Movements</h2>
          <span className="text-xs text-slate-500">Showing last 10 entries</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-100 uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Date</th>
                <th className="py-3 px-4">Part No</th>
                <th className="py-3 px-4">Description</th>
                <th className="py-3 px-4">Type</th>
                <th className="py-3 px-4 text-right">Quantity</th>
                <th className="py-3 px-4">UOM</th>
                <th className="py-3 px-4">Worksheet</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {summary.recent_movements.length > 0 ? (
                summary.recent_movements.map((m: any, idx: number) => (
                  <tr key={m.movement_id || idx} className="hover:bg-slate-50">
                    <td className="py-3 px-4 font-mono font-medium text-slate-900">{m.date}</td>
                    <td className="py-3 px-4 font-mono font-medium text-blue-600">{m.part_no}</td>
                    <td className="py-3 px-4 truncate max-w-xs">{m.description}</td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        m.movement_type === 'IN' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                      }`}>
                        {m.movement_type}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-bold text-slate-900">{m.qty}</td>
                    <td className="py-3 px-4">{m.uom}</td>
                    <td className="py-3 px-4 text-slate-500">{m.source_sheet}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-slate-400">
                    No recent movements recorded.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
