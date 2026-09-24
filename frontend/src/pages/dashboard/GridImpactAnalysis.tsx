import AppLayout from '@/components/AppLayout';
import FrequencyChart from '@/components/dashboard/grid/FrequencyChart';
import GridKPICards from '@/components/dashboard/grid/GridKPICards';
import LoadSolarBalanceChart from '@/components/dashboard/grid/LoadSolarBalanceChart';
import RampRateChart from '@/components/dashboard/grid/RampRateChart';
import ZoneStatusTable from '@/components/dashboard/grid/ZoneStatusTable';
import Topbar from '@/components/Topbar';
import ToastProvider from '@/components/ui/Toast';

export default function GridImpactAnalysis() {
  return (
    <AppLayout>
      <ToastProvider />
      <Topbar
        title="Grid Impact Analysis"
        subtitle="National Grid Stability · STEG Operations"
      />

      <div className="relative flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-screen-2xl space-y-6 px-5 py-6 sm:px-8 lg:px-10 lg:py-8">
          {/* Staggered fade-up — same pattern as your Dashboard.tsx */}
          <div className="animate-fade-up" style={{ animationDelay: '0ms' }}>
            <GridKPICards />
          </div>

          <div
            className="animate-fade-up grid grid-cols-1 gap-6 lg:grid-cols-2"
            style={{ animationDelay: '80ms' }}
          >
            <FrequencyChart />
            <RampRateChart />
          </div>

          <div className="animate-fade-up" style={{ animationDelay: '160ms' }}>
            <LoadSolarBalanceChart />
          </div>

          <div className="animate-fade-up" style={{ animationDelay: '240ms' }}>
            <ZoneStatusTable />
          </div>
        </div>
      </div>
    </AppLayout>
  );
}