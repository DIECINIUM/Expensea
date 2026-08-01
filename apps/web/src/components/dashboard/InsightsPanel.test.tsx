import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { dashboardQueryData } from '../../test/dashboard-fixtures';
import { InsightsPanel } from './InsightsPanel';

describe('InsightsPanel', () => {
  it('renders deterministic changes, contributions, and grounding counts', () => {
    render(<InsightsPanel report={dashboardQueryData.analyticsReport} />);

    expect(
      screen.getByRole('heading', { name: 'Why spending changed' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Food & dining')).toBeInTheDocument();
    expect(screen.getByText('Merchant concentration')).toBeInTheDocument();
    expect(screen.getByText('Grounded by 1 ledger record')).toBeInTheDocument();
  });

  it('states when no conservative rule fires', () => {
    render(
      <InsightsPanel
        report={{
          ...dashboardQueryData.analyticsReport,
          contributions: [],
          insights: [],
        }}
      />,
    );

    expect(
      screen.getByText('No conservative insight rule fired for this period.'),
    ).toBeInTheDocument();
  });
});
