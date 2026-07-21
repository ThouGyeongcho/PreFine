import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { CalendarPage } from "./pages/CalendarPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { MoneyPage } from "./pages/MoneyPage";
import { SystemPage } from "./pages/SystemPage";

function ProtectedPage({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <AppShell>{children}</AppShell>
    </ProtectedRoute>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedPage>
            <DashboardPage />
          </ProtectedPage>
        }
      />
      <Route
        path="/money"
        element={
          <ProtectedPage>
            <MoneyPage />
          </ProtectedPage>
        }
      />
      <Route
        path="/calendar"
        element={
          <ProtectedPage>
            <CalendarPage />
          </ProtectedPage>
        }
      />
      <Route
        path="/system"
        element={
          <ProtectedPage>
            <SystemPage />
          </ProtectedPage>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
