import { DashboardPage } from './components/dashboard/DashboardPage';
import { AppShell } from './components/layout/AppShell';

export function App() {
  return (
    <AppShell>
      <DashboardPage />
    </AppShell>
  );
}
