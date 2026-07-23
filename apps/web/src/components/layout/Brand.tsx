import { clsx } from 'clsx';

interface BrandProps {
  readonly compact?: boolean;
  readonly className?: string;
}

export function Brand({ compact = false, className }: BrandProps) {
  return (
    <div className={clsx('flex items-center gap-3', className)}>
      <span
        className="bg-leaf-500 grid size-9 shrink-0 place-items-center rounded-xl text-white shadow-sm shadow-black/10"
        aria-hidden="true"
      >
        <svg
          viewBox="0 0 24 24"
          className="size-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M5 16.5 9 12l3 2.5 6-7" />
          <path d="M18 7.5h-4" />
          <circle cx="5" cy="16.5" r="1.5" fill="currentColor" stroke="none" />
          <circle cx="9" cy="12" r="1.5" fill="currentColor" stroke="none" />
          <circle cx="12" cy="14.5" r="1.5" fill="currentColor" stroke="none" />
          <circle cx="18" cy="7.5" r="1.5" fill="currentColor" stroke="none" />
        </svg>
      </span>
      {!compact && (
        <span>
          <span className="block text-[15px] font-semibold tracking-tight text-white">
            SpendGraph
          </span>
          <span className="block text-[10px] font-medium tracking-[0.22em] text-white/70 uppercase">
            Intelligence
          </span>
        </span>
      )}
    </div>
  );
}
