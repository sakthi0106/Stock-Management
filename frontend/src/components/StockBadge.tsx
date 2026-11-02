import React from 'react';

interface StockBadgeProps {
  status: 'In Stock' | 'Low Stock' | 'Out of Stock' | 'Unknown' | string;
  className?: string;
}

export const StockBadge: React.FC<StockBadgeProps> = ({ status, className = '' }) => {
  const getBadgeStyle = () => {
    switch (status) {
      case 'In Stock':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'Low Stock':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'Out of Stock':
        return 'bg-rose-50 text-rose-700 border-rose-200';
      case 'Unknown':
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const getDotStyle = () => {
    switch (status) {
      case 'In Stock':
        return 'bg-emerald-500';
      case 'Low Stock':
        return 'bg-amber-500';
      case 'Out of Stock':
        return 'bg-rose-500';
      default:
        return 'bg-slate-400';
    }
  };

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${getBadgeStyle()} ${className}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${getDotStyle()}`} />
      {status}
    </span>
  );
};
