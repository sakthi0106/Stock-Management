import React, { useState, useEffect } from 'react';
import { RefreshCw, Play, Pause, CheckCircle, AlertCircle } from 'lucide-react';
import { fetchApi } from '../api';

export function SyncStatusBar() {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const loadStatus = async () => {
    try {
      const data = await fetchApi<any>('/api/sync/status');
      setStatus(data);
    } catch {
      // ignore transient network glitch
    }
  };

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = async () => {
    setLoading(true);
    try {
      await fetchApi('/api/sync/refresh', { method: 'POST' });
      await loadStatus();
    } finally {
      setLoading(false);
    }
  };

  const handleTogglePause = async () => {
    if (!status) return;
    const endpoint = status.is_paused ? '/api/sync/resume' : '/api/sync/pause';
    await fetchApi(endpoint, { method: 'POST' });
    await loadStatus();
  };

  if (!status) return null;

  return (
    <div className="bg-white border-b border-slate-200 px-6 py-2.5 flex items-center justify-between text-xs text-slate-600">
      <div className="flex items-center space-x-4">
        <span className="flex items-center space-x-1.5 font-medium">
          {status.is_configured ? (
            <>
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-slate-800">Source: <strong className="text-emerald-700">{status.source_title}</strong></span>
            </>
          ) : (
            <>
              <span className="w-2 h-2 rounded-full bg-amber-500"></span>
              <span className="text-slate-800">Source: <strong className="text-amber-700">Not Configured (Demo/Offline)</strong></span>
            </>
          )}
        </span>

        <span className="text-slate-400">|</span>

        <span>Items: <strong className="text-slate-900">{status.total_items}</strong></span>
        <span>Movements: <strong className="text-slate-900">{status.total_movements}</strong></span>
        <span>Worksheets: <strong className="text-slate-900">{status.total_worksheets}</strong></span>

        {status.last_sync_at && (
          <>
            <span className="text-slate-400">|</span>
            <span>Synced: {new Date(status.last_sync_at).toLocaleTimeString()}</span>
          </>
        )}
      </div>

      <div className="flex items-center space-x-2">
        <button
          onClick={handleTogglePause}
          className="flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 transition"
        >
          {status.is_paused ? (
            <>
              <Play className="w-3.5 h-3.5 text-emerald-600" />
              <span>Resume Auto-Sync</span>
            </>
          ) : (
            <>
              <Pause className="w-3.5 h-3.5 text-amber-600" />
              <span>Pause (15s)</span>
            </>
          )}
        </button>

        <button
          onClick={handleRefresh}
          disabled={loading}
          className="flex items-center space-x-1 px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Sync Now</span>
        </button>
      </div>
    </div>
  );
}
