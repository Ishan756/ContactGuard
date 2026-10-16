import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { DashboardLayout } from "./components/layout/DashboardLayout";
import { DashboardOverview } from "./pages/DashboardOverview";
import { AuditQueuePage } from "./pages/AuditQueuePage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { SystemHealthPage } from "./pages/SystemHealthPage";
import { SettingsPage } from "./pages/SettingsPage";

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardLayout />}>
          <Route index element={<DashboardOverview />} />
          <Route path="audits" element={<AuditQueuePage />} />
          <Route path="policies" element={<PoliciesPage />} />
          <Route path="health" element={<SystemHealthPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
