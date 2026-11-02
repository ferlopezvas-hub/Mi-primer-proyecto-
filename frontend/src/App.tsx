import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth } from "./lib/auth";
import { NotificationsPage, ProfilePage, SettingsPage } from "./pages/Account";
import { AccessPending } from "./pages/AccessPending";
import { AdminPage } from "./pages/Admin";
import { BetsPage } from "./pages/Bets";
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage } from "./pages/AuthPages";
import { CalendarPage, LivePage, SearchPage } from "./pages/Browse";
import { Dashboard } from "./pages/Dashboard";
import { MatchDetail, TeamPage } from "./pages/MatchDetail";
import { PredictionsPage } from "./pages/Predictions";

function Protected({ admin = false, children }: { admin?: boolean; children: JSX.Element }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (admin && user.role !== "admin") return <Navigate to="/" replace />;
  if (user.access_active === false) return <AccessPending />;
  return children;
}

function PublicOnly({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  return user ? <Navigate to="/" replace /> : children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="live" element={<LivePage />} />
        <Route path="predictions" element={<PredictionsPage />} />
        <Route path="matches/:id" element={<MatchDetail />} />
        <Route path="teams/:id" element={<TeamPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="bets" element={<BetsPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="admin" element={<Protected admin><AdminPage /></Protected>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
