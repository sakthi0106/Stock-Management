import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  Database, Plus, RefreshCw, Archive, Trash2, CheckCircle2, AlertCircle,
  Clock, Layers, TrendingUp, ChevronDown, ChevronUp, ExternalLink, X,
  Copy, Check, Upload, FileSpreadsheet, ShieldAlert
} from 'lucide-react';
import { apiClient } from '../api/client';
import { SpreadsheetSource, SheetInfo } from '../types';

const SERVICE_ACCOUNT_EMAIL = "stockmanagement@shining-courage-510614-a2.iam.gserviceaccount.com";

interface Props {
  refreshKey?: string | null;
}

// ------------------------------------------------------------------ //
//  Add Source Modal (Google Sheets + Direct Excel Upload)            //
// ------------------------------------------------------------------ //
interface AddModalProps {
  onClose: () => void;
  onAdded: () => void;
}

const AddSourceModal: React.FC<AddModalProps> = ({ onClose, onAdded }) => {
  const [tab, setTab] = useState<'google' | 'upload'>('google');
  const [copied, setCopied] = useState(false);

  // Google Sheets state
  const [googleForm, setGoogleForm] = useState({
    name: '',
    spreadsheet_url_or_id: '',
    period: '',
    description: '',
    is_active: true,
    poll_interval_seconds: 30,
  });

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [uploadPeriod, setUploadPeriod] = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  const [uploadIsActive, setUploadIsActive] = useState(true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const copyEmail = () => {
    navigator.clipboard.writeText(SERVICE_ACCOUNT_EMAIL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleGoogleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!googleForm.name.trim() || !googleForm.spreadsheet_url_or_id.trim()) {
      setError('Name and Google Sheets URL/ID are required.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await apiClient.createSource({
        ...googleForm,
        status: 'active',
      });
      onAdded();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to register spreadsheet source.');
    } finally {
      setSaving(false);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setError('Please select an Excel (.xlsx or .xls) file to upload.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('file', uploadFile);
      fd.append('name', uploadName || uploadFile.name.replace(/\.[^/.]+$/, ''));
      fd.append('period', uploadPeriod);
      fd.append('description', uploadDescription);
      fd.append('is_active', uploadIsActive ? 'true' : 'false');

      await apiClient.uploadSource(fd);
      onAdded();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to upload Excel workbook.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Database size={20} className="text-cyan-600" />
            <h2 className="text-base font-semibold text-slate-800">Add Spreadsheet Source</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400">
            <X size={18} />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-slate-100 bg-slate-50">
          <button
            type="button"
            onClick={() => { setTab('google'); setError(''); }}
            className={`flex-1 py-3 text-xs font-semibold flex items-center justify-center gap-2 border-b-2 transition-all ${
              tab === 'google'
                ? 'border-cyan-600 text-cyan-700 bg-white'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Database size={14} /> Google Sheets URL / ID
          </button>
          <button
            type="button"
            onClick={() => { setTab('upload'); setError(''); }}
            className={`flex-1 py-3 text-xs font-semibold flex items-center justify-center gap-2 border-b-2 transition-all ${
              tab === 'upload'
                ? 'border-cyan-600 text-cyan-700 bg-white'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Upload size={14} /> Upload Excel (.xlsx)
          </button>
        </div>

        {error && (
          <div className="m-5 mb-0 bg-red-50 border border-red-200 text-red-700 rounded-xl p-3 text-xs flex items-start gap-2">
            <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Sync / Access Notice:</p>
              <p className="mt-0.5 leading-relaxed">{error}</p>
            </div>
          </div>
        )}

        {tab === 'google' ? (
          <form onSubmit={handleGoogleSubmit} className="p-5 space-y-4">
            {/* Service Account Reminder Callout */}
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-900">
              <div className="flex items-center gap-1.5 font-bold mb-1 text-amber-950">
                <ShieldAlert size={15} className="text-amber-600" />
                Required: Share your Google Sheet
              </div>
              <p className="text-[11px] text-amber-800 leading-relaxed mb-2">
                Click <b>Share</b> in your Google Sheet and invite this service account with <b>Viewer</b> permission:
              </p>
              <div className="flex items-center gap-2 bg-white px-2.5 py-1.5 rounded-lg border border-amber-300 font-mono text-[11px]">
                <span className="truncate flex-1 select-all">{SERVICE_ACCOUNT_EMAIL}</span>
                <button
                  type="button"
                  onClick={copyEmail}
                  className="text-amber-800 hover:text-amber-950 flex items-center gap-1 font-sans text-[11px] font-semibold bg-amber-100 hover:bg-amber-200 px-2 py-0.5 rounded transition-colors"
                >
                  {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Spreadsheet Label / Name *</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300"
                placeholder="e.g. Switchgear Stock September 2026"
                value={googleForm.name}
                onChange={e => setGoogleForm(f => ({ ...f, name: e.target.value }))}
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Google Sheets URL or ID *</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300"
                placeholder="https://docs.google.com/spreadsheets/d/... or spreadsheet ID"
                value={googleForm.spreadsheet_url_or_id}
                onChange={e => setGoogleForm(f => ({ ...f, spreadsheet_url_or_id: e.target.value }))}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Period</label>
                <input
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300"
                  placeholder="e.g. 2026-09"
                  value={googleForm.period}
                  onChange={e => setGoogleForm(f => ({ ...f, period: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">Sync Interval (seconds)</label>
                <input
                  type="number"
                  min={15}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300"
                  value={googleForm.poll_interval_seconds}
                  onChange={e => setGoogleForm(f => ({ ...f, poll_interval_seconds: Number(e.target.value) }))}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Description (optional)</label>
              <textarea
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300 resize-none"
                rows={2}
                placeholder="Notes or details about this spreadsheet"
                value={googleForm.description}
                onChange={e => setGoogleForm(f => ({ ...f, description: e.target.value }))}
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_active_google"
                checked={googleForm.is_active}
                onChange={e => setGoogleForm(f => ({ ...f, is_active: e.target.checked }))}
                className="rounded border-slate-300 text-cyan-600 focus:ring-cyan-300"
              />
              <label htmlFor="is_active_google" className="text-sm text-slate-700">
                Set as active source immediately
              </label>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 border border-slate-200 text-slate-600 rounded-xl py-2 text-sm font-medium hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="flex-1 bg-cyan-600 text-white rounded-xl py-2 text-sm font-medium hover:bg-cyan-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {saving ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />}
                {saving ? 'Syncing...' : 'Register & Sync'}
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleUploadSubmit} className="p-5 space-y-4">
            {/* File Drop Area */}
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1.5">Select Excel File (.xlsx or .xls) *</label>
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-300 hover:border-cyan-500 rounded-2xl p-6 text-center cursor-pointer bg-slate-50/50 hover:bg-cyan-50/30 transition-all"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx, .xls"
                  className="hidden"
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) {
                      setUploadFile(f);
                      if (!uploadName) setUploadName(f.name.replace(/\.[^/.]+$/, ''));
                    }
                  }}
                />
                <FileSpreadsheet size={36} className="mx-auto text-cyan-600 mb-2" />
                {uploadFile ? (
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{uploadFile.name}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{(uploadFile.size / 1024).toFixed(1)} KB — Click to change</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm font-medium text-slate-700">Click to choose Excel workbook</p>
                    <p className="text-xs text-slate-400 mt-1">Supports multi-worksheet .xlsx and .xls files</p>
                  </div>
                )}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Source Name</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300"
                placeholder="e.g. September 2026 Master"
                value={uploadName}
                onChange={e => setUploadName(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Period (optional)</label>
              <input
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300"
                placeholder="e.g. 2026-09"
                value={uploadPeriod}
                onChange={e => setUploadPeriod(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Description (optional)</label>
              <textarea
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-cyan-300 resize-none"
                rows={2}
                placeholder="Notes about this workbook"
                value={uploadDescription}
                onChange={e => setUploadDescription(e.target.value)}
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_active_upload"
                checked={uploadIsActive}
                onChange={e => setUploadIsActive(e.target.checked)}
                className="rounded border-slate-300 text-cyan-600 focus:ring-cyan-300"
              />
              <label htmlFor="is_active_upload" className="text-sm text-slate-700">
                Set as active source immediately
              </label>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 border border-slate-200 text-slate-600 rounded-xl py-2 text-sm font-medium hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving || !uploadFile}
                className="flex-1 bg-cyan-600 text-white rounded-xl py-2 text-sm font-medium hover:bg-cyan-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {saving ? <RefreshCw size={14} className="animate-spin" /> : <Upload size={14} />}
                {saving ? 'Processing...' : 'Upload & Process'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ //
//  Source Card                                                       //
// ------------------------------------------------------------------ //
interface SourceCardProps {
  source: SpreadsheetSource;
  onRefresh: () => void;
}

const statusBadge = (status: string) => {
  if (status === 'active') return 'bg-emerald-100 text-emerald-700 border border-emerald-200';
  if (status === 'archived') return 'bg-amber-100 text-amber-700 border border-amber-200';
  return 'bg-slate-100 text-slate-600 border border-slate-200';
};

const syncBadge = (s: string) => {
  if (s === 'success') return 'text-emerald-600';
  if (s === 'error') return 'text-red-500';
  if (s === 'warning') return 'text-amber-500';
  return 'text-slate-400';
};

const SourceCard: React.FC<SourceCardProps> = ({ source, onRefresh }) => {
  const [expanded, setExpanded] = useState(false);
  const [sheets, setSheets] = useState<SheetInfo[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [actionError, setActionError] = useState('');
  const [copied, setCopied] = useState(false);

  const loadSheets = async () => {
    try {
      const res = await apiClient.getSourceSheets(source.source_id);
      setSheets(res.sheets);
    } catch {
      setSheets([]);
    }
  };

  const handleExpand = () => {
    if (!expanded) loadSheets();
    setExpanded(v => !v);
  };

  const doSync = async () => {
    setSyncing(true);
    setActionError('');
    try {
      await apiClient.syncSource(source.source_id, true);
      onRefresh();
      if (expanded) loadSheets();
    } catch (e: any) {
      setActionError(e.message || 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const doActivate = async () => {
    setActionError('');
    try {
      await apiClient.activateSource(source.source_id);
      onRefresh();
    } catch (e: any) {
      setActionError(e.message || 'Failed to activate');
    }
  };

  const doArchive = async () => {
    if (!confirm(`Archive "${source.name}"? It will remain accessible for historical view.`)) return;
    setActionError('');
    try {
      await apiClient.archiveSource(source.source_id);
      onRefresh();
    } catch (e: any) {
      setActionError(e.message || 'Failed to archive');
    }
  };

  const doDelete = async () => {
    const isAct = source.is_active === 1;
    const msg = isAct
      ? `Delete active spreadsheet "${source.name}"? Another source will automatically become active.`
      : `Permanently delete "${source.name}" and all its records? This cannot be undone.`;
    if (!confirm(msg)) return;
    setActionError('');
    try {
      await apiClient.deleteSource(source.source_id);
      onRefresh();
    } catch (e: any) {
      setActionError(e.message || 'Failed to delete');
    }
  };

  const handleDeleteSheet = async (sheetName: string) => {
    if (!confirm(`Remove worksheet "${sheetName}" from this source?`)) return;
    try {
      await apiClient.deleteSourceSheet(source.source_id, sheetName);
      loadSheets();
      onRefresh();
    } catch (e: any) {
      alert(`Could not delete sheet: ${e.message}`);
    }
  };

  const copyEmail = () => {
    navigator.clipboard.writeText(SERVICE_ACCOUNT_EMAIL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isLocalFile = source.spreadsheet_id.startsWith('local_file:');
  const syncTime = source.last_sync_at
    ? new Date(source.last_sync_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })
    : 'Never';

  const isPermissionError = source.last_sync_error && (
    source.last_sync_error.includes('403') ||
    source.last_sync_error.includes('404') ||
    source.last_sync_error.toLowerCase().includes('permission') ||
    source.last_sync_error.toLowerCase().includes('cannot access') ||
    source.last_sync_error.toLowerCase().includes('access required')
  );

  return (
    <div className={`bg-white rounded-2xl border shadow-sm overflow-hidden ${source.is_active ? 'border-cyan-300 ring-1 ring-cyan-200' : 'border-slate-200'}`}>
      {/* Header */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <h3 className="font-semibold text-slate-800 text-sm">{source.name}</h3>
              {source.is_active === 1 && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-cyan-100 text-cyan-700 border border-cyan-200">
                  ACTIVE
                </span>
              )}
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize ${statusBadge(source.status)}`}>
                {source.status}
              </span>
              {isLocalFile && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                  📁 Local Excel
                </span>
              )}
            </div>
            {source.description && (
              <p className="text-xs text-slate-500 mb-2">{source.description}</p>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              {source.period && <span>📅 {source.period}</span>}
              <span>🗂 {source.sheets_count} sheet{source.sheets_count !== 1 ? 's' : ''}</span>
              <span>📦 {source.products_count} products</span>
              <span>↕ {source.movements_count} movements</span>
              <span className={`flex items-center gap-1 ${syncBadge(source.last_sync_status)}`}>
                <Clock size={11} /> {syncTime}
              </span>
            </div>

            {/* Permission Denied Notice with 1-Click Copy */}
            {isPermissionError && (
              <div className="mt-3 bg-amber-50 border border-amber-300 rounded-xl p-3 text-xs text-amber-900">
                <p className="font-bold text-amber-950 flex items-center gap-1.5 mb-1">
                  <ShieldAlert size={15} className="text-amber-600" />
                  Google Sheets Access Required
                </p>
                <p className="text-[11px] text-amber-800 leading-relaxed mb-2">
                  Google rejected access (403). Open your spreadsheet in Google Sheets, click <b>Share</b>, and invite:
                </p>
                <div className="flex items-center gap-2 bg-white px-2.5 py-1.5 rounded-lg border border-amber-300 font-mono text-[11px]">
                  <span className="truncate flex-1 select-all">{SERVICE_ACCOUNT_EMAIL}</span>
                  <button
                    type="button"
                    onClick={copyEmail}
                    className="text-amber-800 hover:text-amber-950 flex items-center gap-1 font-sans text-[11px] font-semibold bg-amber-100 hover:bg-amber-200 px-2 py-0.5 rounded transition-colors"
                  >
                    {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                    {copied ? 'Copied' : 'Copy Email'}
                  </button>
                </div>
                <p className="text-[10px] text-amber-700 mt-1.5">
                  After sharing, click <b>Sync Now</b> below to fetch all worksheets.
                </p>
              </div>
            )}

            {source.last_sync_error && !isPermissionError && (
              <p className="text-xs text-red-500 mt-2 truncate">⚠ {source.last_sync_error}</p>
            )}
            {actionError && (
              <p className="text-xs text-red-500 mt-2">{actionError}</p>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2 mt-4">
          <button
            onClick={doSync}
            disabled={syncing}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-cyan-50 text-cyan-700 hover:bg-cyan-100 border border-cyan-200 disabled:opacity-50"
          >
            <RefreshCw size={13} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Syncing...' : 'Sync Now'}
          </button>

          {source.is_active !== 1 && source.status !== 'archived' && (
            <button
              onClick={doActivate}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200"
            >
              <CheckCircle2 size={13} /> Activate
            </button>
          )}

          {source.status !== 'archived' && source.is_active !== 1 && (
            <button
              onClick={doArchive}
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200"
            >
              <Archive size={13} /> Archive
            </button>
          )}

          {/* Delete is ALWAYS available */}
          <button
            onClick={doDelete}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 border border-red-200"
          >
            <Trash2 size={13} /> Delete
          </button>

          {!isLocalFile && source.spreadsheet_id && (
            <a
              href={`https://docs.google.com/spreadsheets/d/${source.spreadsheet_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200"
            >
              <ExternalLink size={13} /> Open Sheet
            </a>
          )}

          <button
            onClick={handleExpand}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200 ml-auto"
          >
            <Layers size={13} />
            {expanded ? 'Hide Worksheets' : 'View Worksheets'}
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </div>
      </div>

      {/* Expanded: Worksheet Details */}
      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50 px-5 py-4">
          {sheets.length === 0 ? (
            <div className="text-center py-6">
              <p className="text-xs text-slate-500 italic">No worksheets discovered yet.</p>
              <p className="text-[11px] text-slate-400 mt-1">
                {isPermissionError
                  ? 'Please share the Google Sheet with the service account and click "Sync Now".'
                  : 'Click "Sync Now" to inspect and load worksheets.'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs text-slate-500 font-semibold mb-1">
                <span>Discovered Worksheets ({sheets.length})</span>
                <span>Actions</span>
              </div>
              {sheets.map(sheet => (
                <div key={sheet.sheet_name} className="bg-white rounded-xl border border-slate-200 p-3 shadow-xs">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-800">{sheet.sheet_name}</span>
                      <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-mono">
                        {sheet.row_count} rows × {sheet.col_count} cols
                      </span>
                    </div>
                    <button
                      onClick={() => handleDeleteSheet(sheet.sheet_name)}
                      title={`Remove ${sheet.sheet_name}`}
                      className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  {sheet.date_columns && sheet.date_columns.length > 0 && (
                    <p className="text-[11px] text-slate-500 mt-1">📅 Date columns: {sheet.date_columns.slice(0, 4).join(', ')}</p>
                  )}
                  {sheet.amount_columns && sheet.amount_columns.length > 0 && (
                    <p className="text-[11px] text-red-500 mt-0.5 font-medium">🚫 Amount fields strictly protected &amp; hidden: {sheet.amount_columns.join(', ')}</p>
                  )}
                  {sheet.issues && sheet.issues.length > 0 && (
                    <div className="mt-1 space-y-0.5">
                      {sheet.issues.slice(0, 2).map((iss, i) => (
                        <p key={i} className="text-[11px] text-amber-600">⚠ {iss}</p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ------------------------------------------------------------------ //
//  Main Page                                                         //
// ------------------------------------------------------------------ //

export function SpreadsheetSources({ refreshKey }: Props) {
  const [sources, setSources] = useState<SpreadsheetSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const fetchSources = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.getSources(true);
      setSources(res.sources);
    } catch (e: any) {
      setError(e.message || 'Failed to load sources');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSources();
  }, [fetchSources, refreshKey]);

  const copyEmail = () => {
    navigator.clipboard.writeText(SERVICE_ACCOUNT_EMAIL);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const active = sources.find(s => s.is_active === 1);
  const activeSources = sources.filter(s => s.status === 'active');
  const archivedSources = sources.filter(s => s.status === 'archived');

  return (
    <div className="space-y-6">
      {/* Top Banner with Service Account Sharing Helper */}
      <div className="bg-gradient-to-r from-cyan-900 to-slate-900 text-white rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Database size={20} className="text-cyan-400" />
              <h1 className="text-lg font-bold">Multi-Spreadsheet Stock Sources</h1>
            </div>
            <p className="text-xs text-slate-300 mt-1 max-w-2xl leading-relaxed">
              Connect multiple Google Spreadsheets or upload direct Excel workbooks (.xlsx). To connect any Google Spreadsheet, share it with your system service account email:
            </p>
          </div>
          <div className="flex items-center gap-2 bg-slate-800/90 border border-slate-700/80 px-3 py-2 rounded-xl text-xs font-mono">
            <span className="text-cyan-300 truncate max-w-xs">{SERVICE_ACCOUNT_EMAIL}</span>
            <button
              onClick={copyEmail}
              className="px-2 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-[11px] font-sans font-semibold rounded-lg flex items-center gap-1 transition-colors flex-shrink-0"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? 'Copied' : 'Copy Email'}
            </button>
          </div>
        </div>
      </div>

      {/* Header Bar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-base font-bold text-slate-800">Registered Spreadsheets ({sources.length})</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Switch the active monthly workbook or view consolidated inventory across all sources.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchSources}
            className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 bg-white text-slate-600 text-sm hover:bg-slate-50"
          >
            <RefreshCw size={15} />
            Refresh
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-600 text-white text-sm font-medium hover:bg-cyan-700 shadow-xs"
          >
            <Plus size={15} />
            Add Spreadsheet
          </button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Total Sources', value: sources.length, icon: Database, color: 'text-cyan-600' },
          { label: 'Active Sources', value: activeSources.length, icon: CheckCircle2, color: 'text-emerald-600' },
          { label: 'Archived Sources', value: archivedSources.length, icon: Archive, color: 'text-amber-600' },
          { label: 'Total Products', value: sources.reduce((s, src) => s + src.products_count, 0), icon: TrendingUp, color: 'text-violet-600' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-1">
              <Icon size={16} className={color} />
              <span className="text-xs text-slate-500 font-medium">{label}</span>
            </div>
            <p className="text-2xl font-bold text-slate-800">{value.toLocaleString()}</p>
          </div>
        ))}
      </div>

      {/* Currently Active Source */}
      {active && (
        <div className="bg-cyan-50 border border-cyan-200 rounded-2xl p-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="h-3 w-3 rounded-full bg-emerald-500 animate-pulse flex-shrink-0" />
            <div>
              <p className="text-sm font-bold text-cyan-900">Current Active Source: {active.name}</p>
              <p className="text-xs text-cyan-700">
                {active.sheets_count} sheets · {active.products_count} catalog products · {active.movements_count} daily transactions
                {active.period ? ` · Period: ${active.period}` : ''}
              </p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-cyan-600 text-white shadow-xs">
            Operational Live Master
          </span>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-3 text-sm flex items-center gap-2">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-400">
          <RefreshCw size={24} className="animate-spin mr-3 text-cyan-600" />
          <span>Loading spreadsheet sources...</span>
        </div>
      ) : sources.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-2xl border border-slate-200 shadow-sm">
          <Database size={40} className="text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">No spreadsheet sources registered</p>
          <p className="text-sm text-slate-400 mt-1">Click "Add Spreadsheet" to register a Google Spreadsheet or upload an Excel file.</p>
          <button
            onClick={() => setShowAdd(true)}
            className="mt-4 px-4 py-2 bg-cyan-600 text-white rounded-xl text-sm font-medium hover:bg-cyan-700"
          >
            <Plus size={14} className="inline mr-1.5" />Add Spreadsheet
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {sources.map(src => (
            <SourceCard key={src.source_id} source={src} onRefresh={fetchSources} />
          ))}
        </div>
      )}

      {showAdd && <AddSourceModal onClose={() => setShowAdd(false)} onAdded={fetchSources} />}
    </div>
  );
}
