import { describe, expect, it } from 'vitest';

import {
  formatLedgerDate,
  formatLedgerMonth,
  formatMoney,
  formatPercentage,
  formatTransactionAmount,
  getTransactionDirection,
} from './ledger-formatters';

describe('ledger formatters', () => {
  it('formats decimal strings without losing Indian grouping or useful precision', () => {
    expect(formatMoney('18540.0000', 'INR')).toBe('₹18,540');
    expect(formatMoney('1234567.8900', 'INR')).toBe('₹12,34,567.89');
    expect(formatMoney('9007199254740993.1250', 'INR')).toBe(
      '₹9,00,71,99,25,47,40,993.125',
    );
    expect(formatMoney('-1250.5000', 'INR')).toBe('-₹1,250.5');
  });

  it('rejects invalid money contracts instead of guessing', () => {
    expect(() => formatMoney('+1.00', 'INR')).toThrow(/decimal strings/i);
    expect(() => formatMoney('1.00001', 'INR')).toThrow(/four fractional/i);
    expect(() => formatMoney('1.00', 'inr')).toThrow(/uppercase iso 4217/i);
  });

  it('formats a service-provided category percentage without deriving it', () => {
    expect(formatPercentage(29)).toBe('29%');
    expect(formatPercentage(-100)).toBe('-100%');
    expect(() => formatPercentage(1.5)).toThrow(/safe whole numbers/i);
  });

  it('formats instants in the account timezone and calendar months as dates', () => {
    expect(formatLedgerDate('2026-07-24T15:01:00Z', 'Asia/Kolkata')).toBe(
      '24 Jul 2026, 8:31 pm',
    );
    expect(formatLedgerDate('2026-07-24T15:01:00Z', 'UTC')).toBe(
      '24 Jul 2026, 3:01 pm',
    );
    expect(formatLedgerMonth('2026-07-01')).toBe('Jul');
  });

  it('rejects malformed dates and non-month-start calendar dates', () => {
    expect(() => formatLedgerDate('not-a-date', 'UTC')).toThrow(/valid iso/i);
    expect(() => formatLedgerMonth('2026-07-02')).toThrow(/valid first day/i);
  });

  it.each([
    ['EXPENSE', 'outflow'],
    ['SHARED_EXPENSE', 'outflow'],
    ['INCOME', 'inflow'],
    ['REFUND', 'inflow'],
    ['TRANSFER', 'neutral'],
  ] as const)('maps %s to the %s presentation direction', (type, direction) => {
    expect(getTransactionDirection(type)).toBe(direction);
  });

  it('adds a display sign from transaction semantics, not amount signs', () => {
    expect(formatTransactionAmount('420.0000', 'INR', 'EXPENSE')).toBe('−₹420');
    expect(formatTransactionAmount('800.0000', 'INR', 'REFUND')).toBe('+₹800');
    expect(formatTransactionAmount('1200.0000', 'INR', 'TRANSFER')).toBe(
      '₹1,200',
    );
  });
});
