import React, { lazy, Suspense, useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { Topbar } from './components/Topbar';
import { SyncStatus } from './components/SyncStatus';
import { apiClient } from './api/client';
import { SyncStatus as SyncStatusType } from './types';

const Dashboard = lazy(() => import('./pages/Dashboard').then(({ Dashboard }) => ({ default: Dashboard })));
const Inventory = lazy(() => import('./pages/Inventory').then(({ Inventory }) => ({ default: Inventory })));
const Movements = lazy(() => import('./pages/Movements').then(({ Movements }) => ({ default: Movements })));
const Reports = lazy(() => import('./pages/Reports').then(({ Reports }) => ({ default: Reports })));
const DataQuality = lazy(() => import('./pages/DataQuality').then(({ DataQuality }) => ({ default: DataQuality })));
const SpreadsheetSources = lazy(() => import('./pages/SpreadsheetSources').then(({ SpreadsheetSources }) => ({ default: SpreadsheetSources })));
const SpreadsheetIntelligence = lazy(() => import('./pages/SpreadsheetIntelligence').then(({ SpreadsheetIntelligence }) => ({ default: SpreadsheetIntelligence })));

export function App() {
  const [currentTab, setCurrentTab] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [inventoryStatusFilter, setInventoryStatusFilter] = useState<string | undefined>(undefined);
  const [selectedSource, setSelectedSource] = useState<string>('active');

  const [syncStatus, setSyncStatus] = useState<SyncStatusType | null>(null);
  const [syncing, setSyncing] = useState(false);

  const fetchSync = async () => {
    try {
      const res = await apiClient.getSyncStatus();
      setSyncStatus(res);
    } catch (e) {
      console.warn('Sync status fetch failed', e);
    }
  };

  useEffect(() => {
    fetchSync();
    const interval = setInterval(fetchSync, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleManualSync = async () => {
    setSyncing(true);
    try {
      const res = await apiClient.triggerSync(selectedSource);
      setSyncStatus(res.status);
    } catch (e) {
      console.error(e);
    } finally {
      setSyncing(false);
    }
  };

  const handleNavigateToInventory = (statusFilter?: string) => {
    setInventoryStatusFilter(statusFilter);
    setCurrentTab('inventory');
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex">
      {/* Sidebar Navigation */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={(tab) => {
          setCurrentTab(tab);
          if (tab !== 'inventory') setInventoryStatusFilter(undefined);
        }}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        syncState={syncStatus?.state}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 lg:pl-72">
        <Topbar
          onOpenSidebar={() => setSidebarOpen(true)}
          syncStatus={syncStatus}
          syncing={syncing}
          onRefresh={handleManualSync}
          searchQuery={searchQuery}
          onSearchChange={(q) => {
            setSearchQuery(q);
            if (q && currentTab !== 'inventory') {
              setCurrentTab('inventory');
            }
          }}
        />

        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          <Suspense fallback={
            <div className="py-24 text-center text-slate-500">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-cyan-600 border-t-transparent mb-3" />
              <p className="text-sm">Loading page...</p>
            </div>
          }>
            {currentTab === 'dashboard' && (
              <Dashboard
                onNavigateToInventory={handleNavigateToInventory}
                onNavigateToMovements={() => setCurrentTab('movements')}
                refreshKey={syncStatus?.lastSuccess}
                selectedSource={selectedSource}
                onSourceChange={setSelectedSource}
              />
            )}
            {currentTab === 'inventory' && (
              <Inventory
                initialStatusFilter={inventoryStatusFilter}
                globalSearch={searchQuery}
                refreshKey={syncStatus?.lastSuccess}
                selectedSource={selectedSource}
                onSourceChange={setSelectedSource}
              />
            )}
            {currentTab === 'movements' && (
              <Movements
                refreshKey={syncStatus?.lastSuccess}
                selectedSource={selectedSource}
                onSourceChange={setSelectedSource}
              />
            )}
            {currentTab === 'reports' && <Reports refreshKey={syncStatus?.lastSuccess} />}
            {currentTab === 'quality' && <DataQuality refreshKey={syncStatus?.lastSuccess} />}
            {currentTab === 'sources' && (
              <SpreadsheetSources refreshKey={syncStatus?.lastSuccess} />
            )}
            {currentTab === 'intelligence' && (
              <SpreadsheetIntelligence refreshKey={syncStatus?.lastSuccess} />
            )}
            {currentTab === 'sync' && (
              <SyncStatus
                status={syncStatus}
                syncing={syncing}
                onRefresh={handleManualSync}
              />
            )}
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export default App;
