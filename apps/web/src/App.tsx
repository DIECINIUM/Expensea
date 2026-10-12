import { DashboardPage } from './components/dashboard/DashboardPage';
import { AppShell } from './components/layout/AppShell';
import { AuthBoundary } from './auth/AuthProvider';

export function App() {
  return (
    <AuthBoundary>
      <AppShell>
        <DashboardPage />
      </AppShell>
    </AuthBoundary>
  );
}
