import { NavLink, Outlet } from 'react-router-dom';
import { Activity, History as HistoryIcon, Info, LayoutDashboard, Package, ScanLine } from 'lucide-react';

interface NavItem {
  to: string;
  label: string;
  Icon: typeof LayoutDashboard;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Overview', Icon: LayoutDashboard, end: true },
  { to: '/scanner', label: 'Live Scanner', Icon: ScanLine },
  { to: '/catalogue', label: 'Catalogue', Icon: Package },
  { to: '/history', label: 'Scan History', Icon: HistoryIcon },
  { to: '/status', label: 'Model & Hardware', Icon: Activity },
  { to: '/about', label: 'About', Icon: Info },
];

export default function Layout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">SP</div>
          <div>
            <div className="brand-name">Smart Product Station</div>
            <div className="brand-sub">recognition · colour · weight</div>
          </div>
        </div>
        <nav>
          {NAV_ITEMS.map(({ to, label, Icon, end }) => (
            <NavLink key={to} to={to} end={end} className="nav-link">
              <Icon className="nav-icon" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">v1.0.0 · localhost demo</div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
