import clsx from "clsx";
import {
  Compass,
  FileUp,
  LayoutDashboard,
  LogOut,
  Mail,
  PieChart,
  Settings,
  UserCheck,
  Users,
} from "lucide-react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";

import { useLogout, useMe } from "../hooks/useAuth";

export const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/donors", label: "Donors", icon: Users },
  { to: "/import", label: "Import", icon: FileUp },
  { to: "/review", label: "Review", icon: UserCheck },
  { to: "/messages", label: "Messages", icon: Mail },
  { to: "/reports", label: "Reports", icon: PieChart },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function Layout() {
  const me = useMe();
  const logout = useLogout();
  const location = useLocation();

  if (me.isPending) {
    return (
      <p role="status" className="p-6 text-slate-700">
        Loading…
      </p>
    );
  }
  if (me.isError) {
    return (
      <p role="alert" className="p-6 text-red-800">
        Could not reach the server. Please reload.
      </p>
    );
  }
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-white focus:p-2"
      >
        Skip to content
      </a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <span className="flex items-center gap-2 font-semibold">
            <Compass aria-hidden="true" className="h-5 w-5 text-indigo-700" />
            CIC Compass
          </span>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden sm:inline">
              {me.data.display_name}
              {me.data.is_super_admin && " (super admin)"}
            </span>
            <button
              type="button"
              onClick={() => logout.mutate()}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-slate-700 hover:bg-slate-100"
            >
              <LogOut aria-hidden="true" className="h-4 w-4" />
              Log out
            </button>
          </div>
        </div>
        <nav aria-label="Main" className="mx-auto max-w-6xl overflow-x-auto px-2">
          <ul className="flex gap-1">
            {NAV.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    clsx(
                      "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm",
                      isActive
                        ? "border-indigo-700 font-semibold text-indigo-800"
                        : "border-transparent text-slate-700 hover:text-slate-900",
                    )
                  }
                >
                  <Icon aria-hidden="true" className="h-4 w-4" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
