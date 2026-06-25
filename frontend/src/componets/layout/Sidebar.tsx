// src/components/layout/Sidebar.tsx
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FolderOpen,
  Bell,
  Shield,
} from "lucide-react";
import { clsx } from "clsx";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/cases",     icon: FolderOpen,      label: "Cases"     },
  { to: "/alerts",    icon: Bell,            label: "Alerts"    },
];

export default function Sidebar() {
  return (
    <aside className="w-56 bg-surface-800 border-r border-surface-700 flex flex-col shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-surface-700">
        <Shield className="text-blue-400" size={22} />
        <span className="font-bold text-white tracking-wide text-sm">
          ZeroRespond
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-blue-600 text-white font-medium"
                  : "text-slate-400 hover:text-slate-100 hover:bg-surface-700"
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-surface-700">
        <p className="text-xs text-slate-500">DPDP Act 2023 Compliant</p>
      </div>
    </aside>
  );
}