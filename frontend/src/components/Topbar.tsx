import { useState } from 'react';
import { RefreshCw, Sun, Moon, LogOut } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

interface TopbarProps {
  title: string;
  subtitle?: string;
  onRefresh?: () => void;
}

export default function Topbar({
  title,
  subtitle,
  onRefresh,
}: TopbarProps) {
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const handleRefresh = () => {
    setIsRefreshing(true);
    onRefresh?.();
    setTimeout(() => {
      setIsRefreshing(false);
      setLastUpdated(
        new Date().toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
        }),
      );
    }, 900);
  };

  /* ---------- Theme ---------- */

  const toggleTheme = () =>
    setTheme(theme === 'dark' ? 'light' : 'dark');

  /* ---------- Logout ---------- */

  const handleLogout = async () => {
    try {
      logout()
      navigate('/');
    } catch {
      // silent — the axios interceptor handles session loss
    }
  };

  /* ---------- Render ---------- */

  return (
    <header className="relative z-10 h-16 glass border-b border-border flex items-center justify-between px-6 shrink-0">
      {/* Left: title + subtitle + updated */}
      <div className="flex items-center gap-4 min-w-0">
        <div className="min-w-0">
          <h1 className="text-base font-semibold text-foreground leading-tight truncate tracking-tight">
            {title}
          </h1>
          {subtitle && (
            <p className="text-xs text-muted-foreground mt-0.5 truncate">
              {subtitle}
            </p>
          )}
        </div>

        {lastUpdated && (
          <span className="hidden md:inline-flex items-center gap-1.5 text-2xs text-muted-foreground bg-muted/70 border border-border px-2.5 py-1 rounded-full shrink-0">
            <span className="relative flex w-1.5 h-1.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-primary opacity-75 animate-ping" />
              <span className="relative inline-flex rounded-full w-1.5 h-1.5 bg-primary" />
            </span>
            Updated {lastUpdated}
          </span>
        )}
      </div>

      {/* Right: refresh, theme, user */}
      <div className="flex items-center gap-2">
        <button
          onClick={handleRefresh}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground bg-muted/70 border border-border rounded-lg px-3 py-1.5 transition-all duration-150 hover:bg-muted active:scale-95"
          title="Refresh data"
        >
          <RefreshCw
            size={13}
            className={isRefreshing ? 'animate-spin text-primary' : ''}
          />
          <span className="hidden sm:inline">Refresh</span>
        </button>

        <button
          onClick={toggleTheme}
          className="flex items-center justify-center w-8 h-8 rounded-lg bg-muted/70 border border-border text-muted-foreground hover:text-foreground hover:border-primary/50 transition-all duration-150 active:scale-95"
          title="Toggle theme"
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        {user && (
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen((o) => !o)}
              className="flex items-center gap-1.5 bg-muted/70 border border-border rounded-lg px-2.5 py-1.5 text-xs font-medium text-foreground hover:border-primary/50 transition-all active:scale-95"
              title={user.email}
            >
              <span className="w-2 h-2 rounded-full bg-primary" />
              <span className="max-w-[120px] truncate">{user.name}</span>
            </button>

            {userMenuOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-card border border-border rounded-lg shadow-xl z-30 overflow-hidden">
                <div className="px-3 py-2.5 border-b border-border">
                  <p className="text-xs font-semibold text-foreground truncate">
                    {user.name}
                  </p>
                  <p className="text-2xs text-muted-foreground truncate mt-0.5">
                    {user.email}
                  </p>
                </div>
                <button
                  onClick={handleLogout}
                  className="w-full px-3 py-2 text-xs text-left flex items-center gap-2 hover:bg-muted transition-colors text-[var(--status-critical)]"
                >
                  <LogOut size={12} />
                  Logout
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom hairline */}
      <span
        aria-hidden
        className="absolute bottom-0 left-0 right-0 h-px opacity-60"
        style={{
          background:
            'linear-gradient(90deg, transparent, var(--chart-1), var(--chart-2), transparent)',
        }}
      />
    </header>
  );
}