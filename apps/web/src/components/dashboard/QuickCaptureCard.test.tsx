import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { QuickCaptureCard } from './QuickCaptureCard';

describe('QuickCaptureCard', () => {
  it('requires enough context to safely interpret a note', async () => {
    const user = userEvent.setup();
    render(<QuickCaptureCard />);

    await user.type(
      screen.getByRole('textbox', { name: /financial note/i }),
      'Paid ₹20',
    );
    await user.click(
      screen.getByRole('button', { name: /check note length/i }),
    );

    expect(
      screen.getByText(/enter at least 12 characters/i),
    ).toBeInTheDocument();
  });

  it('checks a detailed note without sending, saving, or clearing it', async () => {
    const user = userEvent.setup();
    render(<QuickCaptureCard />);
    const note = screen.getByRole('textbox', { name: /financial note/i });

    await user.type(
      note,
      'Lent Priya ₹800 for a cab. She will repay me Friday.',
    );
    await user.click(
      screen.getByRole('button', { name: /check note length/i }),
    );

    expect(screen.getByRole('status')).toHaveTextContent(
      /did not save or send/i,
    );
    expect(note).toHaveValue(
      'Lent Priya ₹800 for a cab. She will repay me Friday.',
    );
  });
});
