import { UserPlus, Users } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { useMutation } from '@apollo/client/react';

import { Card } from './Card';
import type { PersonData } from '../../graphql/dashboard';
import {
  CREATE_PERSON_MUTATION,
  type CreatePersonMutationData,
  type CreatePersonMutationVariables,
} from '../../graphql/phase1-management';
import { mutationProblem } from '../../lib/management-values';

interface PeoplePanelProps {
  readonly people: readonly PersonData[];
  readonly onChanged: () => Promise<void>;
}

export function PeoplePanel({ people, onChanged }: PeoplePanelProps) {
  const [name, setName] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [createPerson] = useMutation<
    CreatePersonMutationData,
    CreatePersonMutationVariables
  >(CREATE_PERSON_MUTATION);

  const clearFeedback = () => {
    setConfirmation(null);
    setSubmissionError(null);
  };

  const submitPerson = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    clearFeedback();
    const normalizedName = name.trim();

    if (!normalizedName) {
      setSubmissionError('Enter a person name.');
      return;
    }

    setIsSaving(true);
    try {
      const response = await createPerson({
        variables: { input: { name: normalizedName } },
      });
      const result = response.data?.createPerson;
      const problem = mutationProblem(result);

      if (problem) {
        setSubmissionError(problem);
        return;
      }
      if (result?.__typename !== 'CreatePersonSuccess') {
        setSubmissionError('The API did not confirm the new person.');
        return;
      }

      setName('');
      try {
        await onChanged();
        setConfirmation('Person saved and the dashboard refreshed.');
      } catch {
        setSubmissionError(
          'Person saved, but the dashboard could not refresh. Retry the dashboard query to see the current list.',
        );
      }
    } catch {
      setSubmissionError(
        'The person could not be saved. Check the API connection and try again.',
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">People</h2>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            Add someone before recording money owed between you.
          </p>
        </div>
        <span
          className="bg-leaf-50 text-leaf-700 grid size-9 shrink-0 place-items-center rounded-xl"
          aria-hidden="true"
        >
          <Users className="size-4" />
        </span>
      </div>

      {people.length > 0 ? (
        <ul
          className="mt-4 flex flex-wrap gap-2"
          aria-label="People in your ledger"
        >
          {people.map((person) => (
            <li
              key={person.id}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-medium text-slate-700"
            >
              {person.name}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 rounded-xl border border-dashed border-slate-200 px-3 py-3 text-[11px] leading-4 text-slate-600">
          No people have been added yet.
        </p>
      )}

      <form
        className="mt-4"
        onSubmit={(event) => {
          void submitPerson(event);
        }}
      >
        <label
          htmlFor="person-name"
          className="text-[11px] font-semibold text-slate-700"
        >
          Person name
        </label>
        <div className="mt-1 flex flex-col gap-2 sm:flex-row">
          <input
            id="person-name"
            value={name}
            required
            maxLength={120}
            autoComplete="name"
            placeholder="Priya Sharma"
            onChange={(event) => {
              setName(event.target.value);
              clearFeedback();
            }}
            className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs text-slate-900 placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={isSaving}
            className="bg-ink-900 hover:bg-ink-800 inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold text-white transition disabled:cursor-wait disabled:opacity-70"
          >
            <UserPlus className="size-3.5" aria-hidden="true" />
            {isSaving ? 'Saving…' : 'Add person'}
          </button>
        </div>

        {confirmation && (
          <p
            className="bg-leaf-50 text-leaf-700 mt-2 rounded-lg px-3 py-2 text-[10px] leading-4"
            role="status"
          >
            {confirmation}
          </p>
        )}
        {submissionError && (
          <p
            className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-4 text-amber-800"
            role="alert"
          >
            {submissionError}
          </p>
        )}
      </form>
    </Card>
  );
}
