import {
  CalendarClock,
  HandCoins,
  ReceiptText,
  WalletCards,
} from 'lucide-react';

import type { SummaryItem, SummaryTone } from '../../lib/demo-data';
import { Card } from './Card';

const toneStyles: Record<
  SummaryTone,
  {
    readonly icon: typeof ReceiptText;
    readonly iconClass: string;
    readonly detailClass: string;
  }
> = {
  emerald: {
    icon: ReceiptText,
    iconClass: 'bg-leaf-50 text-leaf-700',
    detailClass: 'text-leaf-700',
  },
  blue: {
    icon: HandCoins,
    iconClass: 'bg-blue-50 text-blue-700',
    detailClass: 'text-blue-700',
  },
  amber: {
    icon: WalletCards,
    iconClass: 'bg-amber-50 text-amber-700',
    detailClass: 'text-amber-700',
  },
  violet: {
    icon: CalendarClock,
    iconClass: 'bg-violet-50 text-violet-700',
    detailClass: 'text-violet-700',
  },
};

interface SummaryCardProps {
  readonly item: SummaryItem;
}

export function SummaryCard({ item }: SummaryCardProps) {
  const style = toneStyles[item.tone];
  const Icon = style.icon;

  return (
    <Card className="group relative overflow-hidden p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-slate-500">{item.label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-[-0.035em] text-slate-900">
            {item.value}
          </p>
        </div>
        <span
          className={`grid size-10 place-items-center rounded-xl ${style.iconClass}`}
          aria-hidden="true"
        >
          <Icon className="size-[18px]" strokeWidth={1.8} />
        </span>
      </div>
      <p className="mt-4 text-[11px] font-medium text-slate-600">
        {item.detail}
      </p>
      <p className={`mt-1 text-[11px] font-medium ${style.detailClass}`}>
        {item.trend}
      </p>
    </Card>
  );
}
