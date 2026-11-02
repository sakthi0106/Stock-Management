import React from 'react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  variant?: 'emerald' | 'amber' | 'rose' | 'cyan' | 'slate';
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  variant = 'cyan',
}) => {
  const variantStyles = {
    emerald: {
      border: 'border-emerald-200 hover:border-emerald-300',
      iconBg: 'bg-emerald-50 text-emerald-600',
      glow: 'shadow-xs',
    },
    amber: {
      border: 'border-amber-200 hover:border-amber-300',
      iconBg: 'bg-amber-50 text-amber-600',
      glow: 'shadow-xs',
    },
    rose: {
      border: 'border-rose-200 hover:border-rose-300',
      iconBg: 'bg-rose-50 text-rose-600',
      glow: 'shadow-xs',
    },
    cyan: {
      border: 'border-cyan-200 hover:border-cyan-300',
      iconBg: 'bg-cyan-50 text-cyan-600',
      glow: 'shadow-xs',
    },
    slate: {
      border: 'border-slate-200 hover:border-slate-300',
      iconBg: 'bg-slate-100 text-slate-700',
      glow: 'shadow-xs',
    },
  }[variant];

  return (
    <div className={`glass-card p-5 rounded-2xl bg-white border ${variantStyles.border} ${variantStyles.glow} flex flex-col justify-between`}>
      <div className="flex items-start justify-between">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</span>
          <div className="text-2xl sm:text-3xl font-bold text-slate-900 mt-1 tracking-tight">{value}</div>
        </div>
        <div className={`p-3 rounded-xl ${variantStyles.iconBg}`}>
          <Icon size={22} />
        </div>
      </div>
      {subtitle && (
        <div className="mt-3 text-xs text-slate-500 border-t border-slate-100 pt-2 flex items-center justify-between">
          <span>{subtitle}</span>
        </div>
      )}
    </div>
  );
};
