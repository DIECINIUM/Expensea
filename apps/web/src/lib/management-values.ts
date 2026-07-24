const POSITIVE_DECIMAL_PATTERN = /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/;

interface MutationResultLike {
  readonly __typename: string;
  readonly code?: string;
  readonly message?: string;
  readonly field?: string | null;
}

function pad(value: number): string {
  return value.toString().padStart(2, '0');
}

export function isPositiveDecimalString(value: string): boolean {
  return POSITIVE_DECIMAL_PATTERN.test(value) && /[1-9]/.test(value);
}

export function localDateValue(date = new Date()): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function localDateTimeValue(date = new Date()): string {
  return `${localDateValue(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function localDateTimeToIso(value: string): string {
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) {
    throw new RangeError('A valid local date and time is required.');
  }
  return instant.toISOString();
}

export function mutationProblem(
  result: MutationResultLike | null | undefined,
): string | null {
  if (!result) {
    return 'The API returned no mutation result.';
  }
  if (!result.code || !result.message) {
    return null;
  }
  return result.field ? `${result.field}: ${result.message}` : result.message;
}

export function readableEnum(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ');
}
