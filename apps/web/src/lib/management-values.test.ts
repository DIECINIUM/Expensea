import { describe, expect, it } from 'vitest';

import {
  isPositiveDecimalString,
  localDateTimeToIso,
  localDateTimeValue,
  localDateValue,
  mutationProblem,
  readableEnum,
} from './management-values';

describe('management values', () => {
  it('accepts exact positive NUMERIC(19, 4) input without coercion', () => {
    expect(isPositiveDecimalString('420.1250')).toBe(true);
    expect(isPositiveDecimalString('999999999999999.9999')).toBe(true);
    expect(isPositiveDecimalString('0.0000')).toBe(false);
    expect(isPositiveDecimalString('-1.00')).toBe(false);
    expect(isPositiveDecimalString('1.00001')).toBe(false);
  });

  it('creates stable local form values and converts instants explicitly', () => {
    const date = new Date(2026, 6, 24, 20, 31);
    expect(localDateValue(date)).toBe('2026-07-24');
    expect(localDateTimeValue(date)).toBe('2026-07-24T20:31');
    expect(localDateTimeToIso('2026-07-24T20:31')).toBe(date.toISOString());
  });

  it('formats bounded mutation problems and enum labels', () => {
    expect(
      mutationProblem({
        __typename: 'ValidationProblem',
        code: 'INVALID_AMOUNT',
        message: 'Amount is invalid.',
        field: 'amount',
      }),
    ).toBe('amount: Amount is invalid.');
    expect(mutationProblem({ __typename: 'CreatePersonSuccess' })).toBeNull();
    expect(readableEnum('PARTIALLY_PAID')).toBe('Partially Paid');
  });
});
