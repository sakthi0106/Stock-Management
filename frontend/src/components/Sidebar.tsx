import React from 'react';
import { LayoutDashboard, Layers, ArrowLeftRight, FileBarChart, CheckCircle2, RefreshCw, Sparkles, X, Database } from 'lucide-react';

interface SidebarProps {
  currentTab: string;
  onSelectTab: (tab: string) => void;
  isOpen: boolean;
  onClose: () => void;
  syncState?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentTab, onSelectTab, isOpen, onClose, syncState = 'connected' }) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'inventory', label: 'Inventory Master', icon: Layers },
    { id: 'movements', label: 'Stock Movements', icon: ArrowLeftRight },
    { id: 'intelligence', label: 'Spreadsheet Intelligence', icon: Sparkles },
    { id: 'reports', label: 'Reports & Audit', icon: FileBarChart },
    { id: 'quality', label: 'Data Quality', icon: CheckCircle2 },
    { id: 'sources', label: 'Spreadsheet Sources', icon: Database },
    { id: 'sync', label: 'Sync Status', icon: RefreshCw },
  ];

  return (
    <>
      {/* Mobile backdrop overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside className={`
        fixed top-0 bottom-0 left-0 z-50 w-72 bg-white flex flex-col transition-transform duration-300 ease-in-out border-r border-slate-200 shadow-sm
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Brand Header with Company Logo */}
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div className="flex flex-col items-start gap-1">
            <div className="bg-white p-1 rounded-xl flex items-center">
              <img 
                src="/assets/company-logo.webp" 
                alt="Saravanan Electricals Logo" 
                className="h-10 w-auto max-w-[210px] object-contain transition-transform hover:scale-105"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = '/assets/company-logo.png';
                }}
              />
            </div>
            <div className="flex items-center gap-1.5 mt-1 px-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Stock Management System
              </span>
              <span className={`h-2 w-2 rounded-full ${syncState === 'connected' ? 'bg-emerald-500 animate-pulse' : syncState === 'demo' ? 'bg-amber-500' : 'bg-rose-500'}`} />
            </div>
          </div>
          <button 
            onClick={onClose}
            className="lg:hidden p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700"
          >
            <X size={20} />
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  onSelectTab(item.id);
                  onClose();
                }}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all text-left ${
                  isActive
                    ? 'bg-cyan-50 text-cyan-700 border border-cyan-200/80 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <Icon size={18} className={isActive ? 'text-cyan-600' : 'text-slate-400'} />
                <span>{item.label}</span>
                {isActive && (
                  <span className="ml-auto w-1.5 h-4 bg-cyan-600 rounded-full" />
                )}
              </button>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-slate-100 bg-slate-50/80">
          <div className="flex items-center gap-2 mb-1">
            <Sparkles size={14} className="text-amber-500" />
            <span className="text-xs font-semibold text-slate-700">6 Real Worksheets</span>
          </div>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Busbars, Accessories, Cables &amp; Wires, Sleeves, Fab Sheets, and Fasteners.
          </p>
        </div>
      </aside>
    </>
  );
};
