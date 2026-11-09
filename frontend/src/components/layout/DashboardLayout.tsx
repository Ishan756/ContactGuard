import React from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

function pageTitle(pathname: string): string {
  if (pathname === "/") return "Overview";
  if (pathname.startsWith("/upload") || pathname.startsWith("/audits")) return "Upload contracts";
  if (pathname.match(/^\/contracts\/[^/]+\/review/)) return "Contract review";
  if (pathname.match(/^\/findings\/[^/]+\/[^/]+/)) return "Finding detail";
  if (pathname.startsWith("/findings")) return "Findings";
  if (pathname.startsWith("/policies")) return "Policy library";
  if (pathname.startsWith("/history")) return "Review history";
  if (pathname.startsWith("/health")) return "System health";
  if (pathname.startsWith("/settings")) return "Settings";
  return "ContractGuard";
}

export const DashboardLayout: React.FC = () => {
  const location = useLocation();

  return (
    <div className="app-container" id="dashboard-layout">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Sidebar />
      <div className="main-content">
        <Header title={pageTitle(location.pathname)} />
        <main className="page-body" id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};
