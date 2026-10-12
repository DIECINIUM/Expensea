import { z } from 'zod';

import { apiUrl, getCsrfToken } from '../auth/api';

const factSchema = z.object({
  label: z.string().max(160),
  value: z.string().max(100),
  currency: z.string().nullable(),
  record_id: z.string().uuid().nullable(),
  record_kind: z.string().nullable(),
});

const resultSchema = z.object({
  status: z.enum([
    'answered',
    'unsupported',
    'needs_input',
    'busy',
    'resource_limit',
  ]),
  mode: z.enum([
    'deterministic',
    'deterministic_provider_unavailable',
    'structured_intent_deterministic_answer',
  ]),
  tool: z.enum([
    'get_financial_summary',
    'get_transactions',
    'compare_periods',
    'get_outstanding_receivables',
    'get_person_financial_relationship',
    'get_upcoming_recurring',
    'get_transaction_detail',
    'unsupported',
  ]),
  answer: z.string().max(12000),
  facts: z.array(factSchema).max(30),
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
  period_end_inclusive: z.boolean(),
  previous_period_start: z.string().nullable(),
  previous_period_end: z.string().nullable(),
  truncated: z.boolean(),
  limitations: z.array(z.string().max(400)).max(10),
});

export type FinanceAgentResult = z.infer<typeof resultSchema>;
export type FinanceAgentQuestion = {
  question: string;
  currency?: string;
  person_id?: string;
  transaction_id?: string;
};

export async function askFinanceAgent(
  question: FinanceAgentQuestion,
  signal?: AbortSignal,
  endpoint = '/api/agent/questions',
): Promise<FinanceAgentResult> {
  const response = await fetch(apiUrl(endpoint), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': getCsrfToken(),
    },
    body: JSON.stringify(question),
    ...(signal ? { signal } : {}),
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error('Please sign in again before asking about your ledger.');
    }
    if (response.status === 404) {
      throw new Error('Matching ledger data was not found.');
    }
    throw new Error(
      'The finance question could not be completed. Please retry.',
    );
  }
  const text = await response.text();
  if (text.length > 16000)
    throw new Error('The finance answer exceeded its safe limit.');
  try {
    return resultSchema.parse(JSON.parse(text));
  } catch {
    throw new Error('The finance answer was invalid. Please retry.');
  }
}
