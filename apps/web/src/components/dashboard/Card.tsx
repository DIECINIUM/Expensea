import { clsx } from 'clsx';
import type { HTMLAttributes } from 'react';

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        'shadow-card rounded-2xl border border-slate-200/80 bg-white',
        className,
      )}
      {...props}
    />
  );
}
