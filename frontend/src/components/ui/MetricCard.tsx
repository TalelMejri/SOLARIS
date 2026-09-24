import React from 'react';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface MetricCardProps {
  label: string;
  value: string;
  unit?: string;
  trend?: number;
  trendLabel?: string;
  icon?: React.ReactNode;
  subValue?: string;
  subLabel?: string;
  warning?: boolean;
  alert?: boolean;
  className?: string;
}

export default function MetricCard({
  label, value, unit, trend, trendLabel, icon, subValue, subLabel,
  warning, alert, className,
}: MetricCardProps) {
  const positive = (trend ?? 0) >= 0;

  return (
    <div
      className={cn(
        'group relative overflow-hidden card-elevated p-4 flex flex-col justify-between',
        'transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg',
        alert   && 'ring-1 ring-[color-mix(in_oklch,oklch(0.577_0.245_27.325)_40%,transparent)]',
        warning && 'ring-1 ring-[color-mix(in_oklch,var(--accent)_50%,transparent)]',
        className
      )}
    >
      {/* Top accent bar — echoes hero sky on hover, alert/warning when relevant */}
      <span
        aria-hidden
        className={cn(
          'pointer-events-none absolute inset-x-0 top-0 h-[3px] transition-opacity duration-300',
          alert   ? 'opacity-100 bg-gradient-to-r from-[oklch(0.577_0.245_27.325)] to-transparent' :
          warning ? 'opacity-100 bg-gradient-to-r from-[var(--accent)] to-transparent' :
                    'opacity-0 group-hover:opacity-100 bg-gradient-to-r from-[var(--chart-1)] to-[var(--chart-2)]'
        )}
      />

      <div className="flex items-start justify-between gap-2">
        <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {label}
        </p>
        {icon && (
          <span
            className={cn(
              'shrink-0 p-1.5 rounded-md transition-transform duration-300 group-hover:scale-110',
              alert   ? 'bg-status-critical text-status-critical' :
              warning ? 'bg-status-warning  text-status-warning' :
                        'bg-primary/10 text-primary'
            )}
          >
            {icon}
          </span>
        )}
      </div>

      <div className="mt-3 flex items-baseline gap-1.5">
        <span className="text-2xl font-semibold font-tabular text-foreground">
          {value}
        </span>
        {unit && (
          <span className="text-sm text-muted-foreground font-medium">{unit}</span>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between text-2xs gap-2">
        {trend !== undefined && (
          <span
            className={cn(
              'inline-flex items-center gap-0.5 font-semibold px-1.5 py-0.5 rounded-md',
              positive
                ? 'text-primary bg-primary/10'
                : 'text-status-critical bg-status-critical'
            )}
          >
            {positive ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
            {positive ? '+' : ''}{trend}%
          </span>
        )}
        {trendLabel && (
          <span className="text-muted-foreground truncate">{trendLabel}</span>
        )}
        {subValue && (
          <span className="text-muted-foreground whitespace-nowrap">
            <span className="font-tabular font-semibold text-foreground">{subValue}</span>{' '}
            {subLabel}
          </span>
        )}
      </div>
    </div>
  );
}