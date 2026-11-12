import React from 'react';
import { TrendingUp, PieChart as PieChartIcon, BarChart3, ArrowDownRight, ArrowUpRight, Calendar, ArrowRight } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, CartesianGrid
} from 'recharts';
import { DashboardKPI } from '../types';

interface DashboardChartsProps {
  data: DashboardKPI;
  onNavigateToMovements?: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  'In Stock': '#10b981',
  'Low Stock': '#f59e0b',
  'Out of Stock': '#f43f5e',
};

export const DashboardCharts: React.FC<DashboardChartsProps> = ({ data, onNavigateToMovements }) => {
  const trends = data.daily_trends || [];
  const categories = data.category_distribution || [];
  const statusDist = data.status_distribution || [];
  const recentMovs = data.recent_movements || [];

  return (
    <div className="space-y-6">
      {/* Primary Analytics Grid: Daily Transactions & Health Donut */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Daily Movement Chart */}
        <div className="lg:col-span-2 glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col justify-between">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-cyan-50 border border-cyan-100 text-cyan-700">
                <TrendingUp size={16} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Daily Stock Movement Velocity (October 2026)</h3>
                <p className="text-[11px] text-slate-500">Receipts (IN) vs Dispatches (OUT) recorded across worksheets</p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200">
              <span className="flex items-center gap-1.5 text-emerald-700 font-semibold">
                <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Inward (Receipts)
              </span>
              <span className="flex items-center gap-1.5 text-rose-700 font-semibold">
                <span className="w-2.5 h-2.5 rounded-sm bg-rose-500" /> Outward (Dispatches)
              </span>
            </div>
          </div>

          <div className="h-72 w-full min-h-[260px]">
            {trends.length === 0 ? (
              <div className="h-full flex items-center justify-center text-xs text-slate-400">
                No daily transaction activity recorded.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trends} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis
                    dataKey="date"
                    stroke="#94a3b8"
                    fontSize={10}
                    tickLine={false}
                    tickFormatter={(val: string) => val ? val.slice(5) : ''}
                  />
                  <YAxis stroke="#94a3b8" fontSize={10} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      borderColor: '#e2e8f0',
                      borderRadius: '12px',
                      color: '#0f172a',
                      fontSize: '12px',
                      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                    }}
                    formatter={(val: any, name: any) => [
                      `${Number(val).toLocaleString()} units`,
                      name === 'in' ? 'Inward (Receipts)' : 'Outward (Dispatches)'
                    ]}
                    labelFormatter={(label) => `Date: ${label}`}
                  />
                  <Bar dataKey="in" name="in" fill="#10b981" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="out" name="out" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Stock Health Donut */}
        <div className="glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col justify-between">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-1.5 rounded-lg bg-cyan-50 border border-cyan-100 text-cyan-700">
              <PieChartIcon size={16} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Stock Health Distribution</h3>
              <p className="text-[11px] text-slate-500">Current availability status across catalog</p>
            </div>
          </div>

          <div className="h-48 w-full flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusDist}
                  dataKey="count"
                  nameKey="status"
                  cx="50%"
                  cy="50%"
                  innerRadius={52}
                  outerRadius={75}
                  paddingAngle={4}
                >
                  {statusDist.map((entry) => (
                    <Cell key={entry.status} fill={STATUS_COLORS[entry.status] || '#94a3b8'} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    borderColor: '#e2e8f0',
                    borderRadius: '12px',
                    color: '#0f172a',
                    fontSize: '12px',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                  }}
                  formatter={(val: any) => [`${val} items`, 'Count']}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-2 border-t border-slate-100 pt-3">
            {statusDist.map((item) => (
              <div key={item.status} className="flex justify-between items-center text-xs">
                <span className="flex items-center gap-2 text-slate-600 font-medium">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: STATUS_COLORS[item.status] || '#94a3b8' }} />
                  {item.status}
                </span>
                <span className="font-bold text-slate-900">{item.count} items</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Secondary Analytics Row: Category Distribution & Recent Daily Movements Highlights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Category Breakdown */}
        <div className="glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs">
          <div className="flex items-center gap-2 mb-4">
            <div className="p-1.5 rounded-lg bg-cyan-50 border border-cyan-100 text-cyan-700">
              <BarChart3 size={16} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Worksheet / Category Volume</h3>
              <p className="text-[11px] text-slate-500">Product count by operational category</p>
            </div>
          </div>

          <div className="space-y-3">
            {categories.slice(0, 6).map((cat) => {
              const maxCount = Math.max(...categories.map((c) => c.count), 1);
              const pct = Math.round((cat.count / maxCount) * 100);
              return (
                <div key={cat.category} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-medium text-slate-700 truncate max-w-[200px]" title={cat.category}>
                      {cat.category}
                    </span>
                    <span className="font-bold text-slate-900">{cat.count} items</span>
                  </div>
                  <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-cyan-600 rounded-full transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Recent Daily Movements Highlights */}
        <div className="lg:col-span-2 glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-cyan-50 border border-cyan-100 text-cyan-700">
                <Calendar size={16} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Latest Daily Transaction Activity</h3>
                <p className="text-[11px] text-slate-500">Recent store entries recorded in October 2026</p>
              </div>
            </div>
            {onNavigateToMovements && (
              <button
                onClick={onNavigateToMovements}
                className="flex items-center gap-1 text-xs font-semibold text-cyan-600 hover:text-cyan-700 transition-colors"
              >
                <span>View All Movements</span>
                <ArrowRight size={13} />
              </button>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 uppercase tracking-wider text-[10px] text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="py-2 px-3">Date</th>
                  <th className="py-2 px-3">Part No</th>
                  <th className="py-2 px-3">Description</th>
                  <th className="py-2 px-2 text-center">Type</th>
                  <th className="py-2 px-2 text-right">In</th>
                  <th className="py-2 px-2 text-right">Out</th>
                  <th className="py-2 px-2 text-right">Balance</th>
                  <th className="py-2 px-2">UOM</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recentMovs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-slate-400">
                      No recent movement records found.
                    </td>
                  </tr>
                ) : (
                  recentMovs.map((m) => (
                    <tr key={m.movement_id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="py-2 px-3 font-mono font-semibold text-slate-900 whitespace-nowrap">
                        {m.date}
                      </td>
                      <td className="py-2 px-3 font-mono text-cyan-700 font-bold whitespace-nowrap">
                        {m.part_no || m.product_id}
                      </td>
                      <td className="py-2 px-3 truncate max-w-[200px]" title={m.description}>
                        {m.description}
                      </td>
                      <td className="py-2 px-2 text-center whitespace-nowrap">
                        {m.movement_type === 'IN' ? (
                          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <ArrowDownRight size={10} /> IN
                          </span>
                        ) : m.movement_type === 'OUT' ? (
                          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                            <ArrowUpRight size={10} /> OUT
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                            IN/OUT
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-2 text-right font-mono font-medium text-emerald-700">
                        {m.in_qty > 0 ? m.in_qty : '—'}
                      </td>
                      <td className="py-2 px-2 text-right font-mono font-medium text-rose-700">
                        {m.out_qty > 0 ? m.out_qty : '—'}
                      </td>
                      <td className="py-2 px-2 text-right font-mono font-bold text-slate-900">
                        {m.closing_stock !== null ? String(m.closing_stock) : '—'}
                      </td>
                      <td className="py-2 px-2 font-semibold text-slate-500 text-[10px]">
                        {m.uom}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
