import { useEffect, useRef, useState } from 'react';

import {
  askFinanceAgent,
  type FinanceAgentResult,
} from '../../lib/finance-agent-client';
import { Card } from './Card';

export function FinanceAgentPanel() {
  const [question, setQuestion] = useState('');
  const [currency, setCurrency] = useState('');
  const [personId, setPersonId] = useState('');
  const [transactionId, setTransactionId] = useState('');
  const [result, setResult] = useState<FinanceAgentResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const pending = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      pending.current?.abort();
      pending.current = null;
    },
    [],
  );

  async function submit() {
    if (!question.trim() || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setLoading(true);
    setError('');
    setResult(null);
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const answer = await askFinanceAgent(
        {
          question: question.trim(),
          ...(currency ? { currency } : {}),
          ...(personId ? { person_id: personId } : {}),
          ...(transactionId ? { transaction_id: transactionId } : {}),
        },
        controller.signal,
      );
      if (!controller.signal.aborted) setResult(answer);
    } catch (failure) {
      if (pending.current !== controller) return;
      if (controller.signal.aborted) {
        setError('The question timed out. Please retry.');
      } else {
        setError(
          failure instanceof Error
            ? failure.message
            : 'The finance question could not be completed.',
        );
      }
    } finally {
      clearTimeout(timer);
      if (pending.current === controller) {
        pending.current = null;
        setLoading(false);
      }
    }
  }

  return (
    <Card id="finance-agent" className="p-5 sm:p-6">
      <h2 className="text-sm font-semibold text-slate-800">
        Ask your finance ledger
      </h2>
      <p className="mt-1 text-xs text-slate-600">
        Read-only answers from deterministic ledger facts. Try “Why did spending
        change this month?” or “Show recent transactions”. No transfers or
        advice.
      </p>
      <form
        className="mt-4 space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label className="block text-xs text-slate-700">
          Finance question
          <textarea
            className="mt-1 block w-full rounded-lg border border-slate-300 p-2"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={1000}
            required
            disabled={loading}
          />
        </label>
        <label className="block text-xs text-slate-700">
          Currency (optional; summary defaults to profile currency)
          <input
            className="ml-2 rounded border border-slate-300 p-1"
            value={currency}
            maxLength={3}
            pattern="[A-Z]{3}"
            onChange={(event) => setCurrency(event.target.value.toUpperCase())}
            disabled={loading}
          />
        </label>
        <details className="text-xs text-slate-600">
          <summary>Optional owner-local record IDs</summary>
          <label className="mt-2 block">
            Person ID for relationship
            <input
              className="mt-1 block w-full rounded border border-slate-300 p-1"
              value={personId}
              maxLength={36}
              onChange={(event) => setPersonId(event.target.value)}
              disabled={loading}
            />
          </label>
          <label className="mt-2 block">
            Transaction ID for detail
            <input
              className="mt-1 block w-full rounded border border-slate-300 p-1"
              value={transactionId}
              maxLength={36}
              onChange={(event) => setTransactionId(event.target.value)}
              disabled={loading}
            />
          </label>
        </details>
        <button
          className="bg-leaf-700 rounded-lg px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
          disabled={loading || !question.trim()}
          type="submit"
        >
          {loading ? 'Checking ledger…' : 'Ask ledger'}
        </button>
      </form>
      {error && (
        <p role="alert" className="mt-3 text-xs text-red-700">
          {error}
        </p>
      )}
      {result && (
        <section
          aria-label="Finance answer"
          aria-live="polite"
          className="mt-4 text-xs text-slate-700"
        >
          <p className="font-semibold">
            {result.mode === 'deterministic_provider_unavailable'
              ? 'Deterministic fallback — model unavailable or invalid'
              : result.mode === 'structured_intent_deterministic_answer'
                ? 'Model-selected intent; deterministic verified facts'
                : 'Deterministic ledger answer'}
          </p>
          <p className="mt-2 whitespace-pre-line">{result.answer}</p>
          {result.period_start && (
            <p className="mt-2">
              Period: {result.period_start} to {result.period_end}
              {result.period_end_inclusive
                ? ' (inclusive)'
                : ' (end exclusive)'}
              {result.previous_period_start &&
                `; compared with ${result.previous_period_start} to ${result.previous_period_end}`}
            </p>
          )}
          {result.truncated && (
            <p className="mt-2">
              Only a bounded subset is shown; not a complete list.
            </p>
          )}
          <ul className="mt-2 space-y-1" aria-label="Grounding references">
            {result.facts
              .filter((fact) => fact.record_id)
              .map((fact, index) => (
                <li key={`${fact.record_id}-${index}`}>
                  {fact.record_kind} reference: <code>{fact.record_id}</code>
                </li>
              ))}
          </ul>
          <details className="mt-2">
            <summary>Scope and limitations</summary>
            <ul>
              {result.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </Card>
  );
}
