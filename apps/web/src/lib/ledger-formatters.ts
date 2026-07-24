import type { DashboardTransactionType } from '../components/dashboard/types';

const DECIMAL_STRING_PATTERN = /^-?(?:0|[1-9]\d*)(?:\.\d{1,4})?$/;
const NON_NEGATIVE_DECIMAL_STRING_PATTERN = /^(?:0|[1-9]\d*)(?:\.\d{1,4})?$/;
const CURRENCY_CODE_PATTERN = /^[A-Z]{3}$/;
const MONTH_START_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

export type TransactionDirection = 'inflow' | 'outflow' | 'neutral';

function assertDecimalString(amount: string): void {
  if (!DECIMAL_STRING_PATTERN.test(amount)) {
    throw new RangeError(
      'Money values must be decimal strings with at most four fractional digits.',
    );
  }
}

function assertNonNegativeDecimalString(amount: string): void {
  if (!NON_NEGATIVE_DECIMAL_STRING_PATTERN.test(amount)) {
    throw new RangeError(
      'Transaction amounts must be non-negative decimal strings with at most four fractional digits.',
    );
  }
}

function assertCurrencyCode(currency: string): void {
  if (!CURRENCY_CODE_PATTERN.test(currency)) {
    throw new RangeError('Currency values must be uppercase ISO 4217 codes.');
  }
}

function decimalSeparator(locale: string): string {
  return (
    new Intl.NumberFormat(locale)
      .formatToParts(1.1)
      .find((part) => part.type === 'decimal')?.value ?? '.'
  );
}

/**
 * Format an API decimal string without converting the monetary value to a
 * JavaScript number. BigInt preserves the integer portion exactly, while the
 * fractional digits are appended as presentation text.
 */
export function formatMoney(
  amount: string,
  currency: string,
  locale = 'en-IN',
): string {
  assertDecimalString(amount);
  assertCurrencyCode(currency);

  const [integerPart = '0', rawFraction = ''] = amount.split('.');
  const fraction = rawFraction.replace(/0+$/, '');
  const formatter = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
    useGrouping: true,
  });
  const parts = formatter.formatToParts(BigInt(integerPart));
  let lastNumberPartIndex = -1;

  parts.forEach((part, index) => {
    if (part.type === 'integer' || part.type === 'group') {
      lastNumberPartIndex = index;
    }
  });

  return parts
    .map((part, index) => {
      if (index !== lastNumberPartIndex || !fraction) {
        return part.value;
      }

      return `${part.value}${decimalSeparator(locale)}${fraction}`;
    })
    .join('');
}

export function formatPercentage(value: number): string {
  if (!Number.isSafeInteger(value)) {
    throw new RangeError('Category percentages must be safe whole numbers.');
  }
  return `${value}%`;
}

export function formatLedgerDate(
  value: string,
  timeZone: string,
  locale = 'en-IN',
): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new RangeError('Ledger dates must be valid ISO 8601 values.');
  }

  return new Intl.DateTimeFormat(locale, {
    timeZone,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hourCycle: 'h12',
  }).format(date);
}

export function formatLedgerMonth(
  monthStart: string,
  locale = 'en-IN',
): string {
  const match = MONTH_START_PATTERN.exec(monthStart);
  if (!match) {
    throw new RangeError('Ledger months must use the YYYY-MM-DD format.');
  }

  const [, yearValue, monthValue, dayValue] = match;
  const year = Number(yearValue);
  const month = Number(monthValue);
  const day = Number(dayValue);
  const date = new Date(Date.UTC(year, month - 1, day));

  if (
    day !== 1 ||
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1
  ) {
    throw new RangeError('Ledger months must identify a valid first day.');
  }

  return new Intl.DateTimeFormat(locale, {
    timeZone: 'UTC',
    month: 'short',
  }).format(date);
}

export function getTransactionDirection(
  transactionType: DashboardTransactionType,
): TransactionDirection {
  switch (transactionType) {
    case 'EXPENSE':
    case 'SHARED_EXPENSE':
      return 'outflow';
    case 'INCOME':
    case 'REFUND':
      return 'inflow';
    case 'TRANSFER':
      return 'neutral';
  }
}

export function formatTransactionAmount(
  amount: string,
  currency: string,
  transactionType: DashboardTransactionType,
  locale = 'en-IN',
): string {
  assertNonNegativeDecimalString(amount);
  const formattedAmount = formatMoney(amount, currency, locale);
  const direction = getTransactionDirection(transactionType);

  if (direction === 'inflow') {
    return `+${formattedAmount}`;
  }
  if (direction === 'outflow') {
    return `−${formattedAmount}`;
  }
  return formattedAmount;
}
