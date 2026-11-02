import React, { useEffect, useState } from 'react';
import { Database, ChevronDown } from 'lucide-react';
import { apiClient } from '../api/client';
import { SpreadsheetSource } from '../types';

interface SourceSelectorProps {
  value: string;
  onChange: (source: string) => void;
  className?: string;
}

export const SourceSelector: React.FC<SourceSelectorProps> = ({ value, onChange, className = '' }) => {
  const [sources, setSources] = useState<SpreadsheetSource[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.getSources().then(r => {
      setSources(r.sources);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const label = () => {
    if (value === 'active') return 'Active Source';
    if (value === 'all') return 'All Sources (Combined)';
    const found = sources.find(s => s.source_id === value);
    return found ? found.name : value;
  };

  return (
    <div className={`relative inline-flex items-center gap-2 ${className}`}>
      <Database size={15} className="text-cyan-600 flex-shrink-0" />
      <div className="relative">
        <select
          value={value}
          onChange={e => onChange(e.target.value)}
          disabled={loading}
          className="appearance-none bg-white border border-slate-200 rounded-lg text-sm text-slate-700 font-medium pl-3 pr-8 py-1.5 cursor-pointer hover:border-cyan-400 focus:outline-none focus:ring-2 focus:ring-cyan-300 transition-colors"
        >
          <option value="active">Active Source</option>
          <option value="all">All Sources (Combined)</option>
          {sources.map(src => (
            <option key={src.source_id} value={src.source_id}>
              {src.name}{src.status === 'archived' ? ' (archived)' : ''}
            </option>
          ))}
        </select>
        <ChevronDown size={13} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
      </div>
    </div>
  );
};
