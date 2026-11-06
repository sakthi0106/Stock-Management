import React, { useEffect, useState } from 'react';
import { DataQualityReport } from '../types';
import { apiClient } from '../api/client';
import { ShieldAlert, CheckCircle2, AlertTriangle, Info } from 'lucide-react';

interface DataQualityProps {
  refreshKey?: string | null;
}

export const DataQuality: React.FC<DataQualityProps> = ({ refreshKey }) => {
  const [report, setReport] = useState<DataQualityReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.getDataQuality()
      .then((res) => setReport(res))
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  if (loading || !report) {
    return (
      <div className="py-24 text-center text-slate-500">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-cyan-600 border-t-transparent mb-3" />
        <p className="text-sm">Running worksheet schema diagnostics...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight">Data Quality &amp; Schema Integrity</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Audits worksheets for key uniqueness, formula references, special literal values ('NA' and '-'), and amount exclusions
        </p>
      </div>

      {/* Summary KPI */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs">
          <span className="text-xs uppercase font-semibold text-slate-500">Worksheets Inspected</span>
          <div className="text-2xl font-bold text-slate-900 mt-1">{report.sheets_analyzed} Sheets</div>
        </div>
        <div className="glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs">
          <span className="text-xs uppercase font-semibold text-slate-500">Duplicate Keys</span>
          <div className="text-2xl font-bold text-emerald-600 mt-1">{report.duplicate_ids.length} Duplicates</div>
        </div>
        <div className="glass-card p-5 rounded-2xl bg-white border border-slate-200 shadow-xs">
          <span className="text-xs uppercase font-semibold text-slate-500">Integrity Flags</span>
          <div className="text-2xl font-bold text-cyan-600 mt-1">{report.total_issues} Detected</div>
        </div>
      </div>

      {/* Issues List */}
      <div className="glass-card p-6 rounded-2xl bg-white border border-slate-200 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
          <ShieldAlert size={17} className="text-cyan-600" />
          <span>Diagnostic Integrity Findings</span>
        </h3>

        <div className="space-y-3">
          {report.issues.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-600 flex flex-col items-center gap-2">
              <CheckCircle2 size={32} className="text-emerald-500" />
              <span>All worksheets adhere to strict schema rules with zero validation warnings.</span>
            </div>
          ) : (
            report.issues.map((iss, idx) => (
              <div
                key={idx}
                className="p-4 rounded-xl border border-slate-200 bg-slate-50 flex items-start gap-3.5"
              >
                <div className="mt-0.5">
                  {iss.severity === 'WARNING' ? (
                    <AlertTriangle size={18} className="text-amber-500" />
                  ) : (
                    <Info size={18} className="text-cyan-600" />
                  )}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-xs text-slate-800">{iss.type}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                      iss.severity === 'WARNING' ? 'bg-amber-100 text-amber-800' : 'bg-cyan-100 text-cyan-800'
                    }`}>
                      {iss.severity}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 mt-1">{iss.message}</p>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
