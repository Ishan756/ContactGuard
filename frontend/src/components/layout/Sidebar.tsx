import React from "react";
import { NavLink } from "react-router-dom";
import {
  Activity,
  BookOpen,
  FileSearch,
  FileText,
  LayoutDashboard,
  Settings as SettingsIcon,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  id: string;
  end?: boolean;
}

const primaryNav: NavItem[] = [
  { to: "/", label: "Overview", icon: <LayoutDashboard size={18} />, id: "nav-overview", end: true },
  { to: "/upload", label: "Upload contracts", icon: <UploadCloud size={18} />, id: "nav-upload" },
  { to: "/findings", label: "Findings", icon: <FileSearch size={18} />, id: "nav-findings" },
  { to: "/history", label: "Review history", icon: <FileText size={18} />, id: "nav-history" },
  { to: "/policies", label: "Policy library", icon: <BookOpen size={18} />, id: "nav-policies" },
];

const systemNav: NavItem[] = [
  { to: "/health", label: "System health", icon: <Activity size={18} />, id: "nav-health" },
  { to: "/settings", label: "Settings", icon: <SettingsIcon size={18} />, id: "nav-settings" },
];

const renderItem = (item: NavItem) => (
  <li key={item.to}>
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
      id={item.id}
    >
      {item.icon}
      <span>{item.label}</span>
    </NavLink>
  </li>
);

export const Sidebar: React.FC = () => {
  return (
    <aside className="sidebar" id="sidebar-navigation">
      <div className="sidebar-header">
        <div className="logo-badge">
          <ShieldCheck size={22} color="#ffffff" />
        </div>
        <div>
          <div className="logo-title">ContractGuard</div>
          <div className="logo-subtitle">Contract evidence review</div>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary navigation">
        <div className="nav-section-label">Workspace</div>
        <ul className="nav-links">{primaryNav.map(renderItem)}</ul>
        <div className="nav-section-label">Platform</div>
        <ul className="nav-links">{systemNav.map(renderItem)}</ul>
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-footer-line">
          Environment: <span>Local Dev</span>
        </div>
        <div className="sidebar-footer-muted">v0.1.0 · Evidence-first review</div>
      </div>
    </aside>
  );
};
