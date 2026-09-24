import React from 'react';
import { cn } from '@/lib/utils';

export type StatusLevel = 'Normal' | 'Watch' | 'Warning' | 'Critical';

interface StatusBadgeProps {
  status: StatusLevel | string;
  size?: 'sm' | 'md';
  withDot?: boolean;
  className?: string;
}

const statusClasses: Record<string, string> = {
  Normal:   'text-primary bg-status-normal border-[color-mix(in_oklch,var(--primary)_35%,transparent)]',
  Watch:    'text-[oklch(0.55_0.15_230)] bg-status-watch border-[oklch(0.55_0.15_230_/_0.35)]',
  Warning:  'text-status-warning bg-status-warning border-[color-mix(in_oklch,var(--accent)_45%,transparent)]',
  Critical: 'text-status-critical bg-status-critical border-[color-mix(in_oklch,var(--destructive)_45%,transparent)]',
};

const dotClasses: Record<string, string> = {
  Normal:   'bg-primary',
  Watch:    'bg-[oklch(0.55_0.15_230)]',
  Warning:  'bg-accent',
  Critical: 'bg-[var(--destructive)]',
};

export default function StatusBadge({
  status, size = 'md', withDot = true, className,
}: StatusBadgeProps) {
  const cls = statusClasses[status] ?? statusClasses.Normal;
  const dot = dotClasses[status] ?? dotClasses.Normal;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 font-semibold border rounded-full whitespace-nowrap',
        size === 'sm'
          ? 'text-2xs px-2 py-0.5'
          : 'text-xs px-2.5 py-1',
        cls,
        className
      )}
    >
      {withDot && (
        <span className={cn('w-1.5 h-1.5 rounded-full', dot, status === 'Critical' && 'pulse-amber')} />
      )}
      {status}
    </span>
  );
}