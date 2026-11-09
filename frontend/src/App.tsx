import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { DashboardLayout } from "./components/layout/DashboardLayout";
import { DashboardOverview } from "./pages/DashboardOverview";
import { UploadPage } from "./pages/UploadPage";
import { ContractReviewPage } from "./pages/ContractReviewPage";
import { FindingsPage } from "./pages/FindingsPage";
import { FindingDetailPage } from "./pages/FindingDetailPage";
import { PolicyLibraryPage } from "./pages/PolicyLibraryPage";
import { ReviewHistoryPage } from "./pages/ReviewHistoryPage";
import { SystemHealthPage } from "./pages/SystemHealthPage";
import { SettingsPage } from "./pages/SettingsPage";

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardLayout />}>
          <Route index element={<DashboardOverview />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="audits" element={<Navigate to="/upload" replace />} />
          <Route path="contracts/:documentId/review" element={<ContractReviewPage />} />
          <Route path="findings" element={<FindingsPage />} />
          <Route path="findings/:documentId/:findingId" element={<FindingDetailPage />} />
          <Route path="policies" element={<PolicyLibraryPage />} />
          <Route path="history" element={<ReviewHistoryPage />} />
          <Route path="health" element={<SystemHealthPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
