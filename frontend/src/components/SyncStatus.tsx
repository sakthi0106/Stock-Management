import React, { useState } from 'react';
import { SyncStatus as SyncStatusType } from '../types';
import { RefreshCw, CheckCircle, AlertTriangle, Database, FileSpreadsheet, Pause, Play, Clock } from 'lucide-react';
import { apiClient } from '../api/client';

interface SyncStatusProps {
  status: SyncStatusType | null;
  syncing: boolean;
  onRefresh: () => void;
}

export const SyncStatus: React.FC<SyncStatusProps> = ({ status, syncing, onRefresh }) => {
  const [pausing, setPausing] = useState(false);

  if (!status) return null;

  const handleTogglePause = async () => {
    setPausing(true);
    try {
      if (status.is_paused) {
        await apiClient.resumeSync();
      } else {
        await apiClient.pauseSync();
      }
      onRefresh();
    } catch (e) {
      console.error('Failed to toggle sync pause state', e);
    } finally {
      setPausing(false);
    }
  };

  const formatTimestamp = (ts: string | null | undefined) => {
    if (!ts) return 'Never';
    try {
      const d = new Date(ts);
      return d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        dateStyle: 'medium',
        timeStyle: 'medium',
      });
    } catch {
      return ts;
    }
  };

  return (
    <div className="space-y-6">
      {/* Overview Banner */}
      <div className="glass-card p-6 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className={`p-3.5 rounded-2xl ${status.is_live_google_sheet ? 'bg-emerald-50 text-emerald-600' : 'bg-cyan-50 text-cyan-600'}`}>
            <Database size={28} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xl font-bold text-slate-900">
                {status.is_live_google_sheet ? 'Google Sheets Live Connected' : 'Spreadsheet Synchronization Service'}
              </h2>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                status.is_paused ? 'bg-amber-50 text-amber-700 border border-amber-200' :
                status.state === 'connected' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
                status.state === 'demo' ? 'bg-cyan-50 text-cyan-700 border border-cyan-200' :
                'bg-rose-50 text-rose-700 border border-rose-200'
              }`}>
                {status.is_paused ? 'PAUSED' : status.state.toUpperCase()}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1 flex flex-wrap items-center gap-3">
              <span className="flex items-center gap-1 font-semibold text-slate-700">
                <Clock size={12} className="text-cyan-600" />
                Auto-sync: Every {status.poll_interval_seconds || 15}s
              </span>
              <span>•</span>
              <span>Last Synced: <strong>{formatTimestamp(status.lastSuccess)}</strong> (Asia/Kolkata)</span>
              <span>•</span>
              <span>Items: <strong>{status.itemsSynced || 0}</strong></span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleTogglePause}
            disabled={pausing}
            className={`flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl text-xs font-semibold shadow-xs transition-all border ${
              status.is_paused
                ? 'bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border-emerald-200'
                : 'bg-amber-50 hover:bg-amber-100 text-amber-700 border-amber-200'
            }`}
          >
            {status.is_paused ? <Play size={14} /> : <Pause size={14} />}
            <span>{status.is_paused ? 'Resume Auto-Sync' : 'Pause Auto-Sync'}</span>
          </button>

          <button
            onClick={onRefresh}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-sm font-semibold shadow-xs transition-all active:scale-95 disabled:opacity-50"
          >
            <RefreshCw size={16} className={syncing ? 'animate-spin' : ''} />
            <span>{syncing ? 'Synchronizing...' : 'Force Sync Now'}</span>
          </button>
        </div>
      </div>

      {/* Discovered Worksheets Cards */}
      <div>
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700 mb-3 flex items-center gap-2">
          <FileSpreadsheet size={16} className="text-cyan-600" />
          <span>Discovered Worksheets ({(status.sheets || []).length})</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(status.sheets || []).map((s) => {
            const isOk = s.status === 'success' || s.status === 'completed';
            return (
              <div
                key={s.name}
                className="glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-slate-900 text-sm">{s.name}</span>
                    {isOk ? (
                      <CheckCircle size={16} className="text-emerald-500" />
                    ) : (
                      <AlertTriangle size={16} className="text-amber-500" />
                    )}
                  </div>
                  <div className="text-xs text-slate-500 flex items-center gap-4 mt-2">
                    <span>Rows: <strong className="text-slate-800">{s.row_count}</strong></span>
                    <span>Status: <strong className="text-emerald-600">{s.status}</strong></span>
                  </div>
                </div>

                {s.issues && s.issues.length > 0 && (
                  <div className="mt-3 pt-2 border-t border-slate-100 text-[11px] text-amber-700">
                    {s.issues[0]}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
