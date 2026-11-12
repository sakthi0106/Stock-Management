import React from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { LayoutDashboard, ArrowLeftRight, Package, FileSpreadsheet } from 'lucide-react';
import { SyncStatusBar } from './components/SyncStatusBar';
import { Dashboard } from './pages/Dashboard';
import { DailyMovements } from './pages/DailyMovements';
import { InventoryList } from './pages/InventoryList';
import { SpreadsheetSources } from './pages/SpreadsheetSources';

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50 flex flex-col">
        {/* Navigation Header */}
        <header className="bg-slate-900 text-white border-b border-slate-800">
          <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center font-bold text-slate-950 text-sm">
                SM
              </div>
              <span className="font-semibold text-sm tracking-wide">Stock Management</span>
            </div>

            <nav className="flex items-center space-x-1">
              <NavLink
                to="/"
                className={({ isActive }) =>
                  `flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                    isActive ? 'bg-slate-800 text-emerald-400' : 'text-slate-300 hover:bg-slate-800/60'
                  }`
                }
              >
                <LayoutDashboard className="w-4 h-4" />
                <span>Dashboard</span>
              </NavLink>

              <NavLink
                to="/movements"
                className={({ isActive }) =>
                  `flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                    isActive ? 'bg-slate-800 text-emerald-400' : 'text-slate-300 hover:bg-slate-800/60'
                  }`
                }
              >
                <ArrowLeftRight className="w-4 h-4" />
                <span>Daily Movements</span>
              </NavLink>

              <NavLink
                to="/inventory"
                className={({ isActive }) =>
                  `flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                    isActive ? 'bg-slate-800 text-emerald-400' : 'text-slate-300 hover:bg-slate-800/60'
                  }`
                }
              >
                <Package className="w-4 h-4" />
                <span>Inventory Catalog</span>
              </NavLink>

              <NavLink
                to="/sources"
                className={({ isActive }) =>
                  `flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                    isActive ? 'bg-slate-800 text-emerald-400' : 'text-slate-300 hover:bg-slate-800/60'
                  }`
                }
              >
                <FileSpreadsheet className="w-4 h-4" />
                <span>Data Sources</span>
              </NavLink>
            </nav>
          </div>
        </header>

        {/* Global 15s Automatic Sync Status Bar */}
        <SyncStatusBar />

        {/* Content Body */}
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/movements" element={<DailyMovements />} />
            <Route path="/inventory" element={<InventoryList />} />
            <Route path="/sources" element={<SpreadsheetSources />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
