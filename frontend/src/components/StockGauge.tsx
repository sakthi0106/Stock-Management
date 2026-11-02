import React from 'react';
import { SpecialValue } from '../types';

interface StockGaugeProps {
  currentStock: SpecialValue;
  minLevel: number;
  uom: string;
}

export const StockGauge: React.FC<StockGaugeProps> = ({ currentStock, minLevel, uom }) => {
  if (currentStock === 'NA' || currentStock === '-' || currentStock === null || typeof currentStock !== 'number') {
    return (
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-700 font-semibold">
          {currentStock !== null ? String(currentStock) : '—'}
        </span>
        <span className="text-xs text-slate-500">{uom}</span>
      </div>
    );
  }

  const target = Math.max(minLevel * 2.5, 50);
  const percentage = Math.min(100, Math.max(0, (currentStock / target) * 100));

  let barColor = 'bg-emerald-500';
  if (currentStock <= 0) {
    barColor = 'bg-rose-500';
  } else if (currentStock <= minLevel) {
    barColor = 'bg-amber-500';
  }

  return (
    <div className="w-full max-w-[140px] flex flex-col gap-1">
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-bold text-slate-800">
          {currentStock.toLocaleString()} <span className="text-[10px] text-slate-500 font-normal">{uom}</span>
        </span>
        <span className="text-[10px] text-slate-500">Min: {minLevel}</span>
      </div>
      <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};
