import {
  Compass,
  FileUp,
  LayoutDashboard,
  LogOut,
  Mail,
  Menu,
  PieChart,
  Settings,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { useRef, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";

import { useLogout, useMe } from "../hooks/useAuth";
import { BRAND_LOGO } from "../lib/brand";
import { initials } from "../lib/format";
import { ErrorState } from "./Workspace";

export const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/donors", label: "Relationships", icon: Users },
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
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  if (me.isPending)
    return (
      <p role="status" className="session-loading">
        Opening your workspace…
      </p>
    );
  if (me.isError) return <ErrorState error={me.error} retry={() => void me.refetch()} />;
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside
        className="app-rail"
        aria-label="Workspace navigation"
        onKeyDown={(event) => {
          if (event.key === "Escape" && menuOpen) {
            setMenuOpen(false);
            menuButton.current?.focus();
          }
        }}
      >
        <div className="rail-brand">
          <Link to="/donors" className="brand" onClick={() => setMenuOpen(false)}>
            {BRAND_LOGO ? (
              // White plate: the logo must sit on white or dark green, never recolored.
              <span className="brand-logo">
                <img src={BRAND_LOGO} alt="Coding in Color" height={32} />
              </span>
            ) : (
              <Compass size={30} strokeWidth={1.25} aria-hidden="true" />
            )}
            <span>
              CIC Compass<small>CODING IN COLOR</small>
            </span>
          </Link>
          <button
            ref={menuButton}
            className="icon-button mobile-menu-button"
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            onClick={() => setMenuOpen((value) => !value)}
          >
            {menuOpen ? <X size={21} aria-hidden="true" /> : <Menu size={21} aria-hidden="true" />}
          </button>
        </div>
        <nav
          id="main-navigation"
          className={menuOpen ? "rail-navigation is-open" : "rail-navigation"}
          aria-label="Main"
        >
          <p className="rail-label">Stewardship workspace</p>
          <ul>
            {NAV.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink to={to} end={to === "/"} onClick={() => setMenuOpen(false)}>
                  <Icon size={18} strokeWidth={1.6} aria-hidden="true" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="rail-bottom">
          <p className="rail-note">Care, carried forward.</p>
          <div className="account">
            <span className="account-mark" aria-hidden="true">
              {initials(me.data.display_name)}
            </span>
            <span>
              <strong>{me.data.display_name}</strong>
              <small>{me.data.is_super_admin ? "Super admin" : "Board member"}</small>
            </span>
          </div>
          <button
            className="logout-button"
            type="button"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            <LogOut size={16} aria-hidden="true" />
            {logout.isPending ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </aside>
      <main id="main" tabIndex={-1} className="app-workspace">
        <Outlet />
      </main>
    </div>
  );
}
