import React from 'react';
import { Menu, Search, RefreshCw, Clock, ShieldCheck, AlertCircle } from 'lucide-react';
import { SyncStatus } from '../types';

interface TopbarProps {
  onOpenSidebar: () => void;
  syncStatus: SyncStatus | null;
  syncing: boolean;
  onRefresh: () => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}

export const Topbar: React.FC<TopbarProps> = ({
  onOpenSidebar,
  syncStatus,
  syncing,
  onRefresh,
  searchQuery,
  onSearchChange,
}) => {
  const isLive = syncStatus?.is_live_google_sheet;
  const lastSyncTime = syncStatus?.lastSuccess 
    ? new Date(syncStatus.lastSuccess).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : 'Pending';

  return (
    <header className="glass-header sticky top-0 z-30 px-4 lg:px-8 py-3 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenSidebar}
          className="lg:hidden p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100"
        >
          <Menu size={22} />
        </button>

        {/* Global Search */}
        <div className="relative w-64 md:w-80">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search Part No, Product, Description..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-100/90 border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-400 focus:bg-white focus:outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 transition-all"
          />
        </div>
      </div>

      <div className="flex items-center gap-3 sm:gap-4">
        {/* Status Pill */}
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-100 border border-slate-200 text-xs">
          {isLive ? (
            <>
              <ShieldCheck size={14} className="text-emerald-600" />
              <span className="text-slate-700 font-medium">{syncStatus?.source || "Google Sheets Live"}</span>
            </>
          ) : syncStatus?.source && syncStatus.source !== 'Primary Stock Sheet' && syncStatus.source !== 'Default Source' ? (
            <>
              <ShieldCheck size={14} className="text-cyan-600" />
              <span className="text-slate-700 font-medium">{syncStatus.source}</span>
            </>
          ) : (
            <>
              <AlertCircle size={14} className="text-slate-400" />
              <span className="text-slate-500 font-medium">No Spreadsheet Connected</span>
            </>
          )}        </div>

        {/* Last Sync Indicator */}
        <div className="hidden md:flex items-center gap-1.5 text-xs text-slate-500">
          <Clock size={13} />
          <span>Synced: <strong className="text-slate-800">{lastSyncTime}</strong></span>
        </div>

        {/* Manual Refresh Trigger */}
        <button
          onClick={onRefresh}
          disabled={syncing}
          className="flex items-center gap-2 px-3.5 py-1.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-xs font-semibold shadow-xs transition-all active:scale-95 disabled:opacity-50"
          title="Force Synchronize Sheets"
        >
          <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
          <span className="hidden sm:inline">{syncing ? 'Syncing...' : 'Sync Now'}</span>
        </button>
      </div>
    </header>
  );
};
