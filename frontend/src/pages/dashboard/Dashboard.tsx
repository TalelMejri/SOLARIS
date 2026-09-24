// pages/Dashboard.tsx
import AppLayout from '@/components/AppLayout';
import Topbar from '@/components/Topbar';
import ToastProvider from '@/components/ui/Toast';
import WeatherModelStrip from '@/components/dashboard/WeatherModelStrip';
import ForecastBentoGrid from '@/components/dashboard/ForecastBentoGrid';
import ForecastMap from '@/components/dashboard/ForecastMap';
import ForecastChart from '@/components/dashboard/ForecastChart';
import ZoneBreakdownChart from '@/components/dashboard/ZoneBreakdownChart';
import AlertFeed from '@/components/dashboard/AlertFeed';

export default function Dashboard() {
  return (
    <AppLayout>
      <ToastProvider />
      <Topbar
        title="Solar Forecast Dashboard"
        subtitle="National Rooftop PV Network · Tunisia"
      />

      <div className="relative z-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-screen-2xl space-y-6 px-5 py-6 sm:px-8 lg:px-10 lg:py-8">
          <div className="animate-fade-up" style={{ animationDelay: '0ms' }}>
            <ForecastBentoGrid />
          </div>

          <div className="animate-fade-up" style={{ animationDelay: '60ms' }}>
            <WeatherModelStrip />

          </div>

          <div className="animate-fade-up" style={{ animationDelay: '120ms' }}>
            <ForecastMap />
          </div>

          <div className="animate-fade-up" style={{ animationDelay: '180ms' }}>
            <ForecastChart />
          </div>

          <div
            className="animate-fade-up grid grid-cols-1 gap-6 lg:grid-cols-3"
            style={{ animationDelay: '240ms' }}
          >
            <div className="min-w-0 lg:col-span-2">
              <ZoneBreakdownChart />
            </div>
            <div className="min-w-0 lg:col-span-1">
              <AlertFeed />
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}