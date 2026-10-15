import React from "react";
import { NavLink } from "react-router-dom";
import { ShieldCheck, LayoutDashboard, FileSearch, Activity, Settings as SettingsIcon } from "lucide-react";

export const Sidebar: React.FC = () => {
  return (
    <aside className="sidebar" id="sidebar-navigation">
      <div className="sidebar-header">
        <div className="logo-badge">
          <ShieldCheck size={22} color="#ffffff" />
        </div>
        <div>
          <div className="logo-title">ContractGuard</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Multi-Agent Platform</div>
        </div>
      </div>

      <nav style={{ display: "flex", flexDirection: "column", flex: 1 }}>
        <ul className="nav-links">
          <li>
            <NavLink
              to="/"
              end
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              id="nav-overview"
            >
              <LayoutDashboard size={18} />
              <span>Overview</span>
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/audits"
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              id="nav-audits"
            >
              <FileSearch size={18} />
              <span>Audit Queue</span>
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/health"
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              id="nav-health"
            >
              <Activity size={18} />
              <span>System Health</span>
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/settings"
              className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              id="nav-settings"
            >
              <SettingsIcon size={18} />
              <span>Settings</span>
            </NavLink>
          </li>
        </ul>

        <div className="sidebar-footer">
          <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Environment: <span style={{ color: "var(--accent-cyan)", fontWeight: 600 }}>Local Dev</span>
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            v0.1.0 • Multi-Agent Ready
          </div>
        </div>
      </nav>
    </aside>
  );
};
