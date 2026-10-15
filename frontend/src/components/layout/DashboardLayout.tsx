import React from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

export const DashboardLayout: React.FC = () => {
  const location = useLocation();

  const getPageTitle = (path: string) => {
    switch (path) {
      case "/":
        return "Audit Dashboard";
      case "/audits":
        return "Contract Audit Queue";
      case "/health":
        return "System Health & Probes";
      case "/settings":
        return "Platform Settings";
      default:
        return "ContractGuard";
    }
  };

  const title = getPageTitle(location.pathname);

  return (
    <div className="app-container" id="dashboard-layout">
      <Sidebar />
      <div className="main-content">
        <Header title={title} />
        <main className="page-body">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
