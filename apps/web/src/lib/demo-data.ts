export type SummaryTone = 'emerald' | 'blue' | 'amber' | 'violet';

export interface SummaryItem {
  readonly label: string;
  readonly value: string;
  readonly detail: string;
  readonly trend: string;
  readonly tone: SummaryTone;
}

export interface Transaction {
  readonly id: string;
  readonly merchant: string;
  readonly category: string;
  readonly date: string;
  readonly source: string;
  readonly amount: string;
  readonly direction: 'out' | 'in';
  readonly merchantInitials: string;
  readonly merchantTone: string;
}

export const summaryItems: readonly SummaryItem[] = [
  {
    label: 'Spent this month',
    value: '₹18,540',
    detail: 'Across 32 transactions',
    trend: '8.2% below June',
    tone: 'emerald',
  },
  {
    label: 'You owe',
    value: '₹600',
    detail: '1 open payable',
    trend: 'Due in 5 days',
    tone: 'amber',
  },
  {
    label: 'Owed to you',
    value: '₹2,000',
    detail: 'From 2 people',
    trend: '₹800 due Friday',
    tone: 'blue',
  },
  {
    label: 'Upcoming',
    value: '₹1,148',
    detail: '3 recurring payments',
    trend: 'Next: Spotify, 26 Jul',
    tone: 'violet',
  },
];

export const categoryBreakdown = [
  { name: 'Food & dining', amount: '₹5,420', share: 29, color: '#2c9b67' },
  { name: 'Shopping', amount: '₹4,260', share: 23, color: '#315f8c' },
  { name: 'Travel', amount: '₹3,710', share: 20, color: '#d08b45' },
  { name: 'Bills & recurring', amount: '₹2,780', share: 15, color: '#8065a8' },
  { name: 'Other', amount: '₹2,370', share: 13, color: '#8a9892' },
] as const;

export const transactions: readonly Transaction[] = [
  {
    id: 'txn-001',
    merchant: 'Swiggy',
    category: 'Food delivery',
    date: 'Today, 8:31 pm',
    source: 'Email receipt',
    amount: '−₹420',
    direction: 'out',
    merchantInitials: 'SW',
    merchantTone: 'bg-orange-50 text-orange-700',
  },
  {
    id: 'txn-002',
    merchant: 'Priya',
    category: 'Receivable',
    date: 'Today, 4:18 pm',
    source: 'Manual note',
    amount: '+₹800',
    direction: 'in',
    merchantInitials: 'PR',
    merchantTone: 'bg-blue-50 text-blue-700',
  },
  {
    id: 'txn-003',
    merchant: 'Uber',
    category: 'Travel',
    date: 'Yesterday, 9:14 am',
    source: 'Email receipt',
    amount: '−₹286',
    direction: 'out',
    merchantInitials: 'UB',
    merchantTone: 'bg-slate-100 text-slate-700',
  },
  {
    id: 'txn-004',
    merchant: 'Netflix',
    category: 'Entertainment',
    date: '21 Jul, 10:00 am',
    source: 'Recurring',
    amount: '−₹649',
    direction: 'out',
    merchantInitials: 'NF',
    merchantTone: 'bg-red-50 text-red-700',
  },
];

export const spendingPoints = [
  { label: 'Feb', amount: 14200 },
  { label: 'Mar', amount: 16800 },
  { label: 'Apr', amount: 15400 },
  { label: 'May', amount: 21300 },
  { label: 'Jun', amount: 20200 },
  { label: 'Jul', amount: 18540 },
] as const;
