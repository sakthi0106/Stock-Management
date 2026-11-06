import React, { useState, useEffect, useCallback } from 'react';
import {
  Sparkles,
  FileSpreadsheet,
  Layers,
  Search,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Upload,
  ArrowRight,
  Filter,
  Eye,
  SlidersHorizontal,
  ShieldAlert,
  Database,
  Check,
  X,
  FileText,
  Clock,
  HelpCircle,
  TrendingUp,
} from 'lucide-react';
import { apiClient } from '../api/client';
import {
  SpreadsheetSource,
  WorksheetMetadata,
  DynamicColumn,
  DynamicRecord,
  IntelligenceDataQualityReport,
} from '../types';

export const SpreadsheetIntelligence: React.FC<{ refreshKey?: any }> = ({ refreshKey }) => {
  const [activeTab, setActiveTab] = useState<'sources' | 'explorer' | 'mappings' | 'quality'>('sources');

  // Source & Worksheet Selection
  const [sources, setSources] = useState<SpreadsheetSource[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<string>('');
  const [worksheets, setWorksheets] = useState<WorksheetMetadata[]>([]);
  const [selectedSheetName, setSelectedSheetName] = useState<string>('');

  // Explorer Data
  const [records, setRecords] = useState<DynamicRecord[]>([]);
  const [recordColumns, setRecordColumns] = useState<DynamicColumn[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(25);
  const [searchQuery, setSearchQuery] = useState('');

  // Mappings Data
  const [columns, setColumns] = useState<DynamicColumn[]>([]);
  const [savingMapping, setSavingMapping] = useState<number | null>(null);

  // Quality Report Data
  const [qualityReport, setQualityReport] = useState<IntelligenceDataQualityReport | null>(null);

  // Analysis State & Upload
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<string>('');
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [uploadPeriod, setUploadPeriod] = useState('');
  const [uploadDesc, setUploadDesc] = useState('');
  const [uploading, setUploading] = useState(false);
  const [syncingToInventory, setSyncingToInventory] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const showNotification = (message: string, type: 'success' | 'error' = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 4000);
  };

  // Fetch Sources
  const loadSources = useCallback(async () => {
    try {
      const res = await apiClient.getIntelligenceSources();
      setSources(res.sources || []);
      if (!selectedSourceId && res.sources.length > 0) {
        const active = res.sources.find((s) => s.is_active) || res.sources[0];
        setSelectedSourceId(active.source_id);
      }
    } catch (err: any) {
      console.error('Failed to load sources:', err);
    }
  }, [selectedSourceId]);

  useEffect(() => {
    loadSources();
  }, [loadSources, refreshKey]);

  // Fetch Worksheets when source changes
  const loadWorksheets = useCallback(async (sourceId: string) => {
    if (!sourceId) return;
    try {
      const res = await apiClient.getIntelligenceWorksheets(sourceId);
      setWorksheets(res.worksheets || []);
      if (res.worksheets.length > 0) {
        setSelectedSheetName((prev) => {
          const exists = res.worksheets.some((w) => w.sheet_name === prev);
          return exists ? prev : res.worksheets[0].sheet_name;
        });
      } else {
        setSelectedSheetName('');
      }
    } catch (err) {
      console.error('Failed to load worksheets:', err);
    }
  }, []);

  useEffect(() => {
    if (selectedSourceId) {
      loadWorksheets(selectedSourceId);
      loadQualityReport(selectedSourceId);
    }
  }, [selectedSourceId, loadWorksheets, refreshKey]);

  // Load Columns and Records when selected worksheet changes
  const loadSheetDetails = useCallback(async () => {
    if (!selectedSourceId || !selectedSheetName) return;
    try {
      const [colRes, recRes] = await Promise.all([
        apiClient.getIntelligenceColumns(selectedSourceId, selectedSheetName),
        apiClient.getIntelligenceRecords(selectedSourceId, selectedSheetName, page, limit, searchQuery),
      ]);
      setColumns(colRes.columns || []);
      setRecordColumns(colRes.columns || []);
      setRecords(recRes.records || []);
      setRecordsTotal(recRes.total || 0);
    } catch (err) {
      console.error('Failed to load sheet details:', err);
    }
  }, [selectedSourceId, selectedSheetName, page, limit, searchQuery]);

  useEffect(() => {
    if (selectedSourceId && selectedSheetName) {
      loadSheetDetails();
    }
  }, [selectedSourceId, selectedSheetName, page, limit, searchQuery, loadSheetDetails, refreshKey]);

  // Load Quality Report
  const loadQualityReport = async (sourceId: string) => {
    try {
      const rep = await apiClient.getIntelligenceDataQuality(sourceId);
      setQualityReport(rep);
    } catch (err) {
      console.error('Failed to load quality report:', err);
    }
  };

  // Run Universal Analysis
  const handleTriggerAnalysis = async () => {
    if (!selectedSourceId) return;
    setAnalyzing(true);
    setAnalysisProgress('Triggering universal analysis...');
    try {
      const res = await apiClient.triggerIntelligenceAnalysis(selectedSourceId);
      if (res.task_id) {
        // Poll status
        const taskId = res.task_id;
        const interval = setInterval(async () => {
          try {
            const task = await apiClient.getIntelligenceTaskStatus(taskId);
            setAnalysisProgress(task.progress || 'Analyzing worksheets...');
            if (task.status === 'completed') {
              clearInterval(interval);
              setAnalyzing(false);
              showNotification(task.progress || 'Analysis complete!', 'success');
              await loadSources();
              await loadWorksheets(selectedSourceId);
              await loadSheetDetails();
              await loadQualityReport(selectedSourceId);
            } else if (task.status === 'failed') {
              clearInterval(interval);
              setAnalyzing(false);
              showNotification(task.error || 'Analysis failed', 'error');
            }
          } catch (e) {
            clearInterval(interval);
            setAnalyzing(false);
          }
        }, 1500);
      } else {
        setAnalyzing(false);
        showNotification('Analysis triggered successfully', 'success');
        await loadWorksheets(selectedSourceId);
      }
    } catch (err: any) {
      setAnalyzing(false);
      showNotification(err.message || 'Analysis failed', 'error');
    }
  };

  // Handle Excel Upload
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      showNotification('Please select an Excel file', 'error');
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      if (uploadName) formData.append('name', uploadName);
      if (uploadPeriod) formData.append('period', uploadPeriod);
      if (uploadDesc) formData.append('description', uploadDesc);

      const res = await apiClient.uploadIntelligenceSpreadsheet(formData);
      showNotification('Spreadsheet uploaded! Universal discovery in progress...', 'success');
      setIsUploadModalOpen(false);
      setUploadFile(null);
      setUploadName('');
      setUploadPeriod('');
      setUploadDesc('');
      await loadSources();
      setSelectedSourceId(res.source_id);

      if (res.task_id) {
        setAnalyzing(true);
        const taskId = res.task_id;
        const interval = setInterval(async () => {
          try {
            const task = await apiClient.getIntelligenceTaskStatus(taskId);
            setAnalysisProgress(task.progress || 'Extracting and profiling sheets...');
            if (task.status === 'completed') {
              clearInterval(interval);
              setAnalyzing(false);
              showNotification('Spreadsheet analysis completed!', 'success');
              await loadSources();
              await loadWorksheets(res.source_id);
              await loadQualityReport(res.source_id);
            } else if (task.status === 'failed') {
              clearInterval(interval);
              setAnalyzing(false);
              showNotification(task.error || 'Analysis failed', 'error');
            }
          } catch (e) {
            clearInterval(interval);
            setAnalyzing(false);
          }
        }, 1500);
      }
    } catch (err: any) {
      showNotification(err.message || 'Upload failed', 'error');
    } finally {
      setUploading(false);
    }
  };

  // Update Single Column Mapping
  const handleUpdateRole = async (colIndex: number, newRole: string) => {
    if (!selectedSourceId || !selectedSheetName) return;
    setSavingMapping(colIndex);
    try {
      await apiClient.updateIntelligenceColumns(selectedSourceId, selectedSheetName, [
        {
          column_index: colIndex,
          inferred_role: newRole as any,
          mapping_status: 'approved',
          confidence: 1.0,
        },
      ]);
      setColumns((prev) =>
        prev.map((c) =>
          c.column_index === colIndex
            ? { ...c, inferred_role: newRole as any, mapping_status: 'approved', confidence: 1.0, requires_review: 0 }
            : c
        )
      );
      showNotification(`Column mapping updated to ${newRole}`, 'success');
    } catch (err: any) {
      showNotification(err.message || 'Failed to update mapping', 'error');
    } finally {
      setSavingMapping(null);
    }
  };

  // Batch Approve All High Confidence
  const handleApproveAllHighConfidence = async () => {
    if (!selectedSourceId || !selectedSheetName) return;
    const highConf = columns.filter((c) => c.confidence >= 0.8 && c.mapping_status !== 'approved');
    if (highConf.length === 0) {
      showNotification('All high-confidence columns are already approved!', 'success');
      return;
    }
    try {
      await apiClient.updateIntelligenceColumns(
        selectedSourceId,
        selectedSheetName,
        highConf.map((c) => ({
          column_index: c.column_index,
          inferred_role: c.inferred_role,
          mapping_status: 'approved',
          confidence: c.confidence,
        }))
      );
      await loadSheetDetails();
      showNotification(`Approved ${highConf.length} column mappings`, 'success');
    } catch (err: any) {
      showNotification(err.message || 'Failed to approve mappings', 'error');
    }
  };

  // Sync Approved Data to Live Inventory
  const handleSyncToInventory = async () => {
    if (!selectedSourceId) return;
    setSyncingToInventory(true);
    try {
      const res = await apiClient.syncApprovedIntelligenceData(selectedSourceId);
      showNotification(res.message, 'success');
    } catch (err: any) {
      showNotification(err.message || 'Failed to sync to inventory', 'error');
    } finally {
      setSyncingToInventory(false);
    }
  };

  const selectedSource = sources.find((s) => s.source_id === selectedSourceId);
  const currentWorksheet = worksheets.find((w) => w.sheet_name === selectedSheetName);

  return (
    <div className="space-y-6">
      {/* Toast Notification */}
      {notification && (
        <div className="fixed bottom-5 right-5 z-50 animate-in slide-in-from-bottom-3 duration-200">
          <div
            className={`flex items-center gap-3 px-4 py-3 rounded-xl shadow-xl text-xs font-semibold backdrop-blur-md border ${
              notification.type === 'error'
                ? 'bg-rose-900/95 text-rose-100 border-rose-700/50'
                : 'bg-emerald-950/95 text-emerald-100 border-emerald-700/50'
            }`}
          >
            <span>{notification.type === 'error' ? '❌' : '✅'}</span>
            <span>{notification.message}</span>
            <button onClick={() => setNotification(null)} className="ml-2 text-white/60 hover:text-white">
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Top Banner Header */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-cyan-950 rounded-2xl p-6 text-white shadow-md relative overflow-hidden">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-cyan-500/20 text-cyan-300 text-xs font-semibold mb-2 border border-cyan-400/30">
              <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
              Dynamic Spreadsheet Intelligence
            </div>
            <h2 className="text-2xl font-extrabold tracking-tight">Universal Data Recognition & Schema Engine</h2>
            <p className="text-slate-300 text-xs mt-1 max-w-2xl">
              Automatic multi-worksheet discovery, dynamic header scoring, AI semantic column recognition, and complete raw data preservation.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsUploadModalOpen(true)}
              className="px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold rounded-xl text-xs shadow-lg shadow-cyan-600/30 transition-all active:scale-95 flex items-center gap-1.5"
            >
              <Upload className="w-4 h-4" />
              <span>Upload Spreadsheet</span>
            </button>
            <button
              onClick={handleTriggerAnalysis}
              disabled={analyzing || !selectedSourceId}
              className="px-4 py-2.5 bg-white/10 hover:bg-white/20 text-white font-semibold rounded-xl text-xs backdrop-blur-xs transition-all active:scale-95 disabled:opacity-50 flex items-center gap-1.5"
            >
              <RefreshCw className={`w-4 h-4 ${analyzing ? 'animate-spin' : ''}`} />
              <span>{analyzing ? 'Analysing...' : 'Analyse Spreadsheet'}</span>
            </button>
          </div>
        </div>
        {analyzing && (
          <div className="mt-4 pt-3 border-t border-white/10 flex items-center gap-3 text-xs text-cyan-200">
            <div className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            <span>{analysisProgress || 'Extracting and recognizing spreadsheet structures...'}</span>
          </div>
        )}
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 pb-2 overflow-x-auto text-xs font-semibold">
        <button
          onClick={() => setActiveTab('sources')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
            activeTab === 'sources'
              ? 'bg-cyan-600 text-white shadow-xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <Database className="w-4 h-4" />
          <span>Source Management ({sources.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('explorer')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
            activeTab === 'explorer'
              ? 'bg-cyan-600 text-white shadow-xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <FileSpreadsheet className="w-4 h-4" />
          <span>Worksheet Explorer</span>
        </button>

        <button
          onClick={() => setActiveTab('mappings')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
            activeTab === 'mappings'
              ? 'bg-cyan-600 text-white shadow-xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <SlidersHorizontal className="w-4 h-4" />
          <span>Mapping Review</span>
        </button>

        <button
          onClick={() => setActiveTab('quality')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
            activeTab === 'quality'
              ? 'bg-cyan-600 text-white shadow-xs'
              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <ShieldAlert className="w-4 h-4" />
          <span>Data Quality & Integrity</span>
        </button>
      </div>

      {/* Global Source Selector Bar */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-xs flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Active Source:</span>
          <select
            value={selectedSourceId}
            onChange={(e) => setSelectedSourceId(e.target.value)}
            className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-cyan-500"
          >
            {sources.map((s) => (
              <option key={s.source_id} value={s.source_id}>
                {s.name} ({s.source_type === 'excel_upload' ? 'Excel File' : 'Google Sheet'}) {s.period ? `• ${s.period}` : ''}
              </option>
            ))}
          </select>
          {selectedSource && (
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                selectedSource.analysis_status === 'completed'
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : selectedSource.analysis_status === 'analyzing'
                  ? 'bg-amber-50 text-amber-700 border border-amber-200 animate-pulse'
                  : 'bg-slate-100 text-slate-600'
              }`}
            >
              {selectedSource.analysis_status || 'Analyzed'}
            </span>
          )}
        </div>

        {activeTab !== 'sources' && worksheets.length > 0 && (
          <div className="flex items-center gap-3">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Worksheet:</span>
            <select
              value={selectedSheetName}
              onChange={(e) => setSelectedSheetName(e.target.value)}
              className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-cyan-500"
            >
              {worksheets.map((w) => (
                <option key={w.sheet_name} value={w.sheet_name}>
                  {w.sheet_name} ({w.row_count} rows, {w.col_count} cols) [{w.classification}]
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* ============================================================== */}
      {/* TAB 1: SOURCE MANAGEMENT                                       */}
      {/* ============================================================== */}
      {activeTab === 'sources' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Registered Sources</div>
              <div className="text-2xl font-black text-slate-900 mt-1">{sources.length}</div>
              <div className="text-[11px] text-slate-500 mt-1">
                {sources.filter((s) => s.source_type === 'excel_upload').length} Excel Files,{' '}
                {sources.filter((s) => s.source_type !== 'excel_upload').length} Google Sheets
              </div>
            </div>
            <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Discovered Worksheets</div>
              <div className="text-2xl font-black text-cyan-600 mt-1">{worksheets.length}</div>
              <div className="text-[11px] text-slate-500 mt-1">Available in active spreadsheet</div>
            </div>
            <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Raw Records Lineage</div>
              <div className="text-2xl font-black text-emerald-600 mt-1">
                {selectedSource?.total_records || recordsTotal || 0}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Extracted without missing values or truncated columns</div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Configured Spreadsheet Sources</h3>
                <p className="text-xs text-slate-500">Universal discovery status, periodic tracking, and data profiling</p>
              </div>
              <button
                onClick={() => setIsUploadModalOpen(true)}
                className="px-3.5 py-1.5 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-all"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>Upload New Excel</span>
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs whitespace-nowrap">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/60 text-slate-500 uppercase font-semibold">
                    <th className="py-3 px-4">Source Name</th>
                    <th className="py-3 px-4">Type</th>
                    <th className="py-3 px-4">Worksheets</th>
                    <th className="py-3 px-4">Total Rows</th>
                    <th className="py-3 px-4">Analysis Status</th>
                    <th className="py-3 px-4">Last Analysed</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sources.map((s) => (
                    <tr
                      key={s.source_id}
                      onClick={() => setSelectedSourceId(s.source_id)}
                      className={`hover:bg-cyan-50/40 cursor-pointer transition-colors ${
                        selectedSourceId === s.source_id ? 'bg-cyan-50/60 font-semibold' : ''
                      }`}
                    >
                      <td className="py-3 px-4">
                        <div className="font-bold text-slate-900">{s.name}</div>
                        <div className="text-[10px] font-mono text-slate-400">{s.source_id}</div>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            s.source_type === 'excel_upload'
                              ? 'bg-purple-50 text-purple-700 border border-purple-200'
                              : 'bg-blue-50 text-blue-700 border border-blue-200'
                          }`}
                        >
                          {s.source_type === 'excel_upload' ? 'Excel Upload' : 'Google Sheets'}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono">{s.total_worksheets || s.sheets_count || worksheets.length || '—'}</td>
                      <td className="py-3 px-4 font-mono">{s.total_records || s.products_count || '—'}</td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                            s.analysis_status === 'completed'
                              ? 'bg-emerald-50 text-emerald-700'
                              : s.analysis_status === 'analyzing'
                              ? 'bg-amber-50 text-amber-700 animate-pulse'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {s.analysis_status || 'Ready'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-500 text-[11px]">
                        {s.last_analyzed_at ? new Date(s.last_analyzed_at).toLocaleString() : s.last_sync_at || 'Never'}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedSourceId(s.source_id);
                            handleTriggerAnalysis();
                          }}
                          className="px-2.5 py-1 text-cyan-600 hover:text-cyan-800 font-bold hover:bg-cyan-50 rounded-lg transition-colors"
                        >
                          Run Analysis
                        </button>
                      </td>
                    </tr>
                  ))}
                  {sources.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-400">
                        No sources registered. Upload an Excel file or connect Google Sheets above.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 2: WORKSHEET EXPLORER                                      */}
      {/* ============================================================== */}
      {activeTab === 'explorer' && (
        <div className="space-y-4">
          {/* Worksheet Header Card */}
          {currentWorksheet && (
            <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-bold text-slate-900">{currentWorksheet.sheet_name}</h3>
                  <span className="px-2 py-0.5 rounded-full bg-cyan-50 text-cyan-700 border border-cyan-200 text-[10px] font-bold uppercase">
                    {currentWorksheet.classification.replace('_', ' ')}
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold">
                    Quality: {currentWorksheet.quality_score}%
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  Header Row: #{currentWorksheet.header_row} • Extracted: {currentWorksheet.row_count} rows • Discovered:{' '}
                  {currentWorksheet.col_count} columns
                </p>
              </div>

              {/* Actions & Search Bar */}
              <div className="flex items-center gap-2.5">
                <button
                  onClick={handleTriggerAnalysis}
                  disabled={analyzing}
                  className="px-3 py-2 text-xs font-semibold bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-xl shadow-2xs flex items-center gap-1.5 transition-all disabled:opacity-50"
                  title="Re-analyze rows and columns for this sheet"
                >
                  <RefreshCw className={`w-3.5 h-3.5 text-cyan-600 ${analyzing ? 'animate-spin' : ''}`} />
                  <span className="hidden sm:inline">Re-Analyze Sheet</span>
                </button>

                <div className="relative min-w-[240px]">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search across all columns..."
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setPage(1);
                    }}
                    className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-hidden focus:ring-2 focus:ring-cyan-500"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Dynamic Records Table */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
            <div className="overflow-x-auto max-h-[600px]">
              <table className="w-full text-left text-xs whitespace-nowrap">
                <thead className="sticky top-0 z-10">
                  <tr className="border-b border-slate-200 bg-slate-100/90 backdrop-blur-xs text-slate-600 uppercase font-bold tracking-wider">
                    <th className="py-3 px-3 w-12 text-center bg-slate-200/50">#Row</th>
                    {recordColumns.map((col) => (
                      <th key={col.column_index} className="py-3 px-4">
                        <div className="flex flex-col">
                          <span className="text-slate-800">{col.original_col}</span>
                          <span
                            className={`text-[9px] font-mono lowercase tracking-normal px-1 py-0.2 rounded w-fit mt-0.5 ${
                              col.inferred_role === 'unknown'
                                ? 'bg-slate-200 text-slate-600'
                                : 'bg-cyan-100 text-cyan-800'
                            }`}
                          >
                            {col.inferred_role}
                          </span>
                        </div>
                      </th>
                    ))}
                    {recordColumns.length === 0 && (
                      <th className="py-3 px-4 text-slate-400">Loading columns...</th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {records.map((rec) => (
                    <tr key={rec.id || rec.row_index} className="hover:bg-slate-50 transition-colors">
                      <td className="py-2.5 px-3 font-mono text-[11px] text-slate-400 text-center bg-slate-50/50">
                        {rec.row_index}
                      </td>
                      {recordColumns.map((col) => {
                        const val = rec.raw_data[col.original_col];
                        const isLiteral = val === 'NA' || val === 'N/A' || val === '-';
                        return (
                          <td
                            key={col.column_index}
                            className={`py-2.5 px-4 ${
                              isLiteral ? 'font-mono text-amber-700 bg-amber-50/30 font-semibold' : 'text-slate-700'
                            }`}
                          >
                            {val !== undefined && val !== null && val !== '' ? String(val) : <span className="text-slate-300">—</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  {records.length === 0 && (
                    <tr>
                      <td colSpan={recordColumns.length + 1} className="py-12 text-center text-slate-400">
                        No records found. Click "Analyse Spreadsheet" to extract and profile records.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Toolbar */}
            <div className="p-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 bg-slate-50/50">
              <div>
                Showing {records.length} of {recordsTotal} rows • Page {page}
              </div>
              <div className="flex items-center gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1 bg-white border border-slate-200 rounded-lg font-semibold hover:bg-slate-100 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  disabled={records.length < limit || page * limit >= recordsTotal}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-3 py-1 bg-white border border-slate-200 rounded-lg font-semibold hover:bg-slate-100 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 3: MAPPING REVIEW                                          */}
      {/* ============================================================== */}
      {activeTab === 'mappings' && (
        <div className="space-y-4">
          <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="text-base font-bold text-slate-900">Semantic Column Review & Approval</h3>
              <p className="text-xs text-slate-500">
                Verify AI suggestions, correct ambiguous columns, and promote validated inventory to live tables.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleApproveAllHighConfidence}
                className="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-all"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Approve All High-Confidence (&gt;80%)</span>
              </button>
              <button
                onClick={handleSyncToInventory}
                disabled={syncingToInventory || !selectedSourceId}
                className="px-3.5 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-all disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${syncingToInventory ? 'animate-spin' : ''}`} />
                <span>{syncingToInventory ? 'Syncing...' : 'Sync Approved to Live Inventory'}</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {columns.map((col) => {
              const confPct = Math.round(col.confidence * 100);
              const confBadge =
                confPct >= 80
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : confPct >= 50
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200';

              return (
                <div
                  key={col.column_index}
                  className={`bg-white rounded-2xl border p-4 shadow-xs flex flex-col justify-between transition-all ${
                    col.requires_review
                      ? 'border-amber-300 ring-1 ring-amber-200 bg-amber-50/10'
                      : 'border-slate-200 hover:border-cyan-300'
                  }`}
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-bold text-slate-900 text-xs break-all">{col.original_col}</div>
                        <div className="text-[10px] font-mono text-slate-400">Index #{col.column_index + 1}</div>
                      </div>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${confBadge}`}>
                        {confPct}% Conf
                      </span>
                    </div>

                    {/* Role Dropdown */}
                    <div>
                      <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                        Inferred Role
                      </label>
                      <select
                        value={col.inferred_role}
                        onChange={(e) => handleUpdateRole(col.column_index, e.target.value)}
                        className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-cyan-500"
                      >
                        <option value="product_id">Product Identifier (Part No / SKU)</option>
                        <option value="description">Product Description / Item Name</option>
                        <option value="category">Category / Group / Material Type</option>
                        <option value="uom">Unit of Measurement (UOM)</option>
                        <option value="unit_price">Unit Price (Currency / Rate)</option>
                        <option value="opening_stock">Opening Stock Quantity</option>
                        <option value="in_qty">Inward / Received Quantity</option>
                        <option value="out_qty">Outward / Issued Quantity</option>
                        <option value="closing_stock">Closing Stock Quantity</option>
                        <option value="date">Date / Timeline</option>
                        <option value="unknown">Unknown / Custom Business Field</option>
                      </select>
                    </div>

                    {/* Sample Values */}
                    <div>
                      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                        Sample Values:
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {col.sample_values?.slice(0, 4).map((s, i) => (
                          <span
                            key={i}
                            className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-[10px] font-mono max-w-[120px] truncate"
                          >
                            {String(s)}
                          </span>
                        ))}
                        {(!col.sample_values || col.sample_values.length === 0) && (
                          <span className="text-[10px] text-slate-400 italic">No sample values</span>
                        )}
                      </div>
                    </div>

                    {col.reason && <p className="text-[10px] text-slate-500 italic mt-1">{col.reason}</p>}
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-xs">
                    <span
                      className={`text-[10px] font-bold ${
                        col.mapping_status === 'approved' ? 'text-emerald-600' : 'text-slate-400'
                      }`}
                    >
                      {col.mapping_status === 'approved' ? '✓ Approved' : 'Suggested by AI/ML'}
                    </span>
                    <button
                      onClick={() => handleUpdateRole(col.column_index, col.inferred_role)}
                      disabled={savingMapping === col.column_index}
                      className="px-2.5 py-1 bg-slate-100 hover:bg-cyan-50 hover:text-cyan-700 text-slate-700 font-bold rounded-lg transition-colors text-[11px]"
                    >
                      {col.mapping_status === 'approved' ? 'Re-Approve' : 'Approve Mapping'}
                    </button>
                  </div>
                </div>
              );
            })}
            {columns.length === 0 && (
              <div className="col-span-full py-12 text-center text-slate-400">
                Select a worksheet to view and review column mappings.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* TAB 4: DATA QUALITY & INTEGRITY DASHBOARD                      */}
      {/* ============================================================== */}
      {activeTab === 'quality' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Overall Quality Score</div>
              <div className="text-3xl font-black text-emerald-600 mt-1">
                {qualityReport?.overall_quality_score || 100}%
              </div>
              <div className="w-full bg-slate-100 h-1.5 rounded-full mt-2 overflow-hidden">
                <div
                  className="bg-emerald-500 h-full rounded-full transition-all duration-500"
                  style={{ width: `${qualityReport?.overall_quality_score || 100}%` }}
                />
              </div>
            </div>

            <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Total Columns Discovered</div>
              <div className="text-3xl font-black text-slate-900 mt-1">
                {qualityReport?.total_columns || 0}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">
                {qualityReport?.recognized_fields || 0} mapped • {qualityReport?.unknown_fields || 0} custom
              </div>
            </div>

            <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Duplicate Candidates</div>
              <div className="text-3xl font-black text-amber-600 mt-1">
                {qualityReport?.duplicate_candidates?.length || 0}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Flagged without merging records</div>
            </div>

            <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Requires Review</div>
              <div className="text-3xl font-black text-cyan-600 mt-1">
                {qualityReport?.requires_review_count || 0}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Confidence &lt; 80% or ambiguous</div>
            </div>
          </div>

          {/* Quality Issues / Anomaly Alerts */}
          <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <span>Data Quality Warnings & Integrity Checks</span>
            </h3>

            <div className="space-y-2">
              {qualityReport?.quality_issues?.map((iss, i) => (
                <div
                  key={i}
                  className="p-3 rounded-xl bg-amber-50/60 border border-amber-200/80 text-xs text-amber-900 flex items-start gap-2.5"
                >
                  <span className="font-bold text-amber-600 mt-0.5">•</span>
                  <span>{iss}</span>
                </div>
              ))}

              {(!qualityReport?.quality_issues || qualityReport.quality_issues.length === 0) && (
                <div className="py-6 text-center text-slate-400 text-xs">
                  <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                  <p className="font-semibold text-slate-700">No critical schema or integrity issues detected.</p>
                  <p className="text-slate-400 mt-0.5">All discovered worksheets follow recognized structure.</p>
                </div>
              )}
            </div>

            {/* Duplicate Candidates List */}
            {qualityReport?.duplicate_candidates && qualityReport.duplicate_candidates.length > 0 && (
              <div className="mt-5 pt-4 border-t border-slate-100">
                <h4 className="text-xs font-bold text-slate-800 mb-2">Duplicate Product Identifiers Found:</h4>
                <div className="flex flex-wrap gap-1.5">
                  {qualityReport.duplicate_candidates.map((d, i) => (
                    <span
                      key={i}
                      className="px-2 py-1 bg-rose-50 text-rose-700 border border-rose-200 rounded-lg text-xs font-mono font-semibold"
                    >
                      {d}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ============================================================== */}
      {/* UPLOAD MODAL                                                   */}
      {/* ============================================================== */}
      {isUploadModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 animate-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Upload className="w-4 h-4 text-cyan-600" />
                <span>Upload New Excel Spreadsheet</span>
              </h3>
              <button
                onClick={() => setIsUploadModalOpen(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleUploadSubmit} className="mt-4 space-y-4 text-xs">
              <div>
                <label className="font-bold text-slate-700 block mb-1">Select Excel File (.xlsx, .xls) *</label>
                <input
                  type="file"
                  required
                  accept=".xlsx,.xls"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-cyan-50 file:text-cyan-700 hover:file:bg-cyan-100"
                />
              </div>

              <div>
                <label className="font-bold text-slate-700 block mb-1">Spreadsheet Display Name</label>
                <input
                  type="text"
                  placeholder="e.g. November 2026 Stock Master"
                  value={uploadName}
                  onChange={(e) => setUploadName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="font-bold text-slate-700 block mb-1">Month / Period</label>
                <input
                  type="text"
                  placeholder="e.g. 2026-11"
                  value={uploadPeriod}
                  onChange={(e) => setUploadPeriod(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="font-bold text-slate-700 block mb-1">Description / Notes</label>
                <textarea
                  rows={2}
                  placeholder="e.g. Monthly stock register containing switchgear and fasteners"
                  value={uploadDesc}
                  onChange={(e) => setUploadDesc(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl resize-none"
                />
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsUploadModalOpen(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading}
                  className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white font-semibold rounded-xl shadow-xs disabled:opacity-50 flex items-center gap-1.5"
                >
                  {uploading ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Uploading & Analysing...</span>
                    </>
                  ) : (
                    <span>Upload & Discover</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
