import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowRight, FileText, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';

import { Card } from './Card';

const quickCaptureSchema = z.object({
  note: z
    .string()
    .trim()
    .min(12, 'Enter at least 12 characters for this length-only check.')
    .max(240, 'Keep the note under 240 characters.'),
});

type QuickCaptureValues = z.infer<typeof quickCaptureSchema>;

export function QuickCaptureCard() {
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<QuickCaptureValues>({
    resolver: zodResolver(quickCaptureSchema),
    defaultValues: { note: '' },
  });
  const noteLength = useWatch({ control, name: 'note' }).length;

  const submitNote = () => {
    setConfirmation(
      'Length check passed. This Phase 0 demo did not save or send your note.',
    );
  };

  return (
    <Card
      id="quick-capture"
      className="border-ink-800 bg-ink-900 relative overflow-hidden p-5 text-white sm:p-6"
    >
      <div
        className="bg-leaf-500/10 pointer-events-none absolute -top-14 -right-12 size-44 rounded-full blur-2xl"
        aria-hidden="true"
      />
      <div className="relative">
        <div className="flex items-center gap-2">
          <span className="text-leaf-200 grid size-8 place-items-center rounded-lg bg-white/10">
            <Sparkles className="size-4" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-sm font-semibold">Quick capture</h2>
            <p className="text-[10px] font-medium text-white/70">
              Length check only · never saved
            </p>
          </div>
        </div>

        <form
          className="mt-5"
          noValidate
          onSubmit={(event) => void handleSubmit(submitNote)(event)}
        >
          <label htmlFor="financial-note" className="sr-only">
            Financial note
          </label>
          <div className="relative">
            <FileText
              className="absolute top-3.5 left-3.5 size-4 text-white/65"
              aria-hidden="true"
            />
            <textarea
              id="financial-note"
              rows={4}
              maxLength={240}
              placeholder="e.g. Lent Priya ₹800 for a cab today. She'll repay me Friday."
              aria-describedby={
                errors.note
                  ? 'financial-note-error financial-note-count'
                  : 'financial-note-count'
              }
              aria-invalid={Boolean(errors.note)}
              {...register('note', {
                onChange: () => setConfirmation(null),
              })}
              className="focus:border-leaf-200/60 focus:ring-leaf-500/20 w-full resize-none rounded-xl border border-white/15 bg-white/[0.08] py-3 pr-3 pl-10 text-xs leading-relaxed text-white placeholder:text-white/65 focus:ring-2"
            />
          </div>
          <div className="mt-1.5 flex min-h-5 items-start justify-between gap-3">
            <p
              id="financial-note-error"
              className="text-[10px] leading-4 text-amber-200"
            >
              {errors.note?.message}
            </p>
            <span
              id="financial-note-count"
              className="shrink-0 text-[10px] font-medium text-white/70"
            >
              {noteLength}/240
            </span>
          </div>
          <button
            type="submit"
            className="bg-leaf-500 hover:bg-leaf-600 mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition"
          >
            Check note length
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </button>
          {confirmation && (
            <p
              className="text-leaf-100 mt-3 rounded-lg bg-white/[0.06] px-3 py-2 text-[10px] leading-4"
              role="status"
            >
              {confirmation}
            </p>
          )}
        </form>
      </div>
    </Card>
  );
}
