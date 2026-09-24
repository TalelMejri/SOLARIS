import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Zap, ChevronLeft, ChevronRight, Bell, Settings,
  HelpCircle, Activity, Map, BarChart3, Radio, LogOut, User as UserIcon,
  Loader2, Shield,
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

interface NavItem {
  id: string; label: string; href: string;
  icon: React.ReactNode; badge?: number; group: string;
}

const navItems: NavItem[] = [
  { id: 'nav-dashboard', label: 'Solar Forecast', href: '/dashboard', icon: <LayoutDashboard size={18} />, group: 'core' },
  { id: 'nav-grid', label: 'Grid Impact', href: '/dashboard/grid-impact', icon: <Zap size={18} />, badge: 3, group: 'core' },
  { id: 'nav-installations', label: 'Installations', href: '/dashboard/installations', icon: <Radio size={18} />, badge: 2, group: 'core' },

];

const groupLabels: Record<string, string> = {
  core: 'Operations',
};

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const groups = ['core', 'data', 'ops'];

  const [menuOpen, setMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const displayName = user?.name ?? 'Guest';
  const initials = user?.name?.trim()?.[0]?.toUpperCase() ?? 'U';

  // Close the dropdown on outside click / Escape
  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  const handleLogout = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    setLogoutError(null);
    try {
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      console.error('Logout failed', err);
      setLogoutError('Could not sign out. Please try again.');
      setIsLoggingOut(false);
    }
  };

  return (
    <aside
      className={`relative z-20 flex flex-col h-screen glass border-r border-sidebar-border sidebar-transition shrink-0 ${collapsed ? 'w-16' : 'w-64'
        }`}
    >
      {/* Brand */}
      <div className={`flex items-center h-16 border-b border-sidebar-border px-4 ${collapsed ? 'justify-center' : 'gap-3'
        }`}>
        {!collapsed && (
          <div className="flex flex-col leading-none min-w-0">
            <span className="font-semibold text-base text-sidebar-foreground tracking-tight">
              Solaris
            </span>
            <span className="text-2xs text-muted-foreground mt-0.5 truncate">
              Grid Intelligence
            </span>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-2.5 space-y-6">
        {groups.map((group) => {
          const items = navItems.filter((n) => n.group === group);
          return (
            <div key={`group-${group}`}>
              {!collapsed && (
                <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-muted-foreground px-2.5 mb-2">
                  {groupLabels[group]}
                </p>
              )}
              <ul className="space-y-1">
                {items.map((item) => {
                  const isActive =
                    item.href === '/dashboard'
                      ? pathname === '/dashboard'
                      : item.href !== '#' && pathname.startsWith(item.href);
                  return (
                    <li key={item.id}>
                      <Link
                        to={item.href}
                        title={collapsed ? item.label : undefined}
                        className={`group relative flex items-center gap-3 px-2.5 py-2 rounded-lg text-sm font-medium transition-all duration-150 ${isActive
                          ? 'bg-sidebar-primary/10 text-sidebar-primary shadow-[inset_0_0_0_1px_color-mix(in_oklch,var(--sidebar-primary)_25%,transparent)]'
                          : 'text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-muted'
                          } ${collapsed ? 'justify-center' : ''}`}
                      >
                        <span className={`shrink-0 transition-colors ${isActive
                          ? 'text-sidebar-primary'
                          : 'text-muted-foreground group-hover:text-sidebar-foreground'
                          }`}>
                          {item.icon}
                        </span>
                        {!collapsed && <span className="truncate">{item.label}</span>}
                        {!collapsed && item.badge && (
                          <span className="ml-auto bg-sidebar-primary/15 text-sidebar-primary text-2xs font-semibold px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
                            {item.badge}
                          </span>
                        )}
                        {collapsed && item.badge && (
                          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-sidebar-accent ring-2 ring-sidebar" />
                        )}
                        {isActive && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-sidebar-primary rounded-r-full" />
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      {/* User / Logout */}
      <div className={`relative border-t border-sidebar-border p-3 ${collapsed ? 'flex justify-center' : ''}`} ref={menuRef}>
        {logoutError && !collapsed && (
          <div role="alert" className="mb-2 text-2xs text-red-500 px-1.5">
            {logoutError}
          </div>
        )}

        <button
          type="button"
          onClick={() => setMenuOpen((v) => !v)}
          disabled={isLoggingOut}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label={`Account menu for ${displayName}`}
          title={collapsed ? displayName : undefined}
          className={`flex items-center gap-2.5 rounded-lg hover:bg-muted p-1.5 transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-wait ${collapsed ? '' : 'w-full text-left'
            }`}
        >
          <div className="relative w-8 h-8 rounded-full bg-gradient-to-br from-sidebar-primary to-sidebar-accent flex items-center justify-center shrink-0">
            {isLoggingOut ? (
              <Loader2 size={14} className="text-white animate-spin" />
            ) : (
              <span className="text-xs font-semibold text-white">{initials}</span>
            )}
            {!isLoggingOut && (
              <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-sidebar" />
            )}
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-sm font-medium text-sidebar-foreground truncate">
                {displayName}
              </p>
              {user?.email && (
                <p className="text-2xs text-muted-foreground truncate">{user.email}</p>
              )}
            </div>
          )}
        </button>

        {/* Dropdown menu */}
        {menuOpen && !collapsed && (
          <div
            role="menu"
            className="absolute bottom-16 left-3 right-3 rounded-lg border border-border bg-card shadow-lg overflow-hidden z-30"
          >
            <div className="px-3 py-2 border-b border-border">
              <p className="text-xs font-semibold text-foreground truncate">{displayName}</p>
              {user?.email && (
                <p className="text-2xs text-muted-foreground truncate">{user.email}</p>
              )}
            </div>

            <button
              role="menuitem"
              type="button"
              onClick={() => { setMenuOpen(false); navigate('/dashboard/profile'); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors text-left"
            >
              <UserIcon size={14} className="text-muted-foreground" />
              Profile
            </button>
            <button
              role="menuitem"
              type="button"
              onClick={() => { setMenuOpen(false); navigate('/dashboard/settings'); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors text-left"
            >
              <Shield size={14} className="text-muted-foreground" />
              Security
            </button>

            <div className="border-t border-border">
              <button
                role="menuitem"
                type="button"
                onClick={handleLogout}
                disabled={isLoggingOut}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-500 hover:bg-red-500/10 transition-colors text-left disabled:opacity-60 disabled:cursor-wait"
              >
                {isLoggingOut ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <LogOut size={14} />
                )}
                {isLoggingOut ? 'Signing out…' : 'Sign out'}
              </button>
            </div>
          </div>
        )}

        {/* Collapsed mode: avatar itself is the logout trigger */}
        {collapsed && (
          <button
            type="button"
            onClick={handleLogout}
            disabled={isLoggingOut}
            title="Sign out"
            aria-label="Sign out"
            className="absolute inset-0 cursor-pointer disabled:cursor-wait"
          />
        )}
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 w-6 h-6 rounded-full bg-card border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:border-primary hover:bg-primary/5 transition-all duration-150 z-30 shadow-md"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </aside>
  );
}