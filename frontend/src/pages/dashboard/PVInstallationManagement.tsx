import AppLayout from '@/components/AppLayout';
import InstallationKPICards from '@/components/dashboard/installation/InstallationKPICards';
import InstallationTable from '@/components/dashboard/installation/InstallationTable';
import Topbar from '@/components/Topbar';
import ToastProvider from '@/components/ui/Toast';


export default function PVInstallationManagement() {
    return (
        <AppLayout>
            <ToastProvider />
            <Topbar
                title="PV Installation Management"
                subtitle="National Rooftop Registry · 1,963 Registered Units"
                lastUpdated="8 min ago"
            />

            <div className="relative flex-1 overflow-y-auto">
                <div className="mx-auto w-full max-w-screen-2xl space-y-6 px-5 py-6 sm:px-8 lg:px-10 lg:py-8">
                    <div className="animate-fade-up" style={{ animationDelay: '0ms' }}>
                        <InstallationKPICards />
                    </div>
                    <div className="animate-fade-up" style={{ animationDelay: '80ms' }}>
                        <InstallationTable />
                    </div>
                </div>
            </div>
        </AppLayout>
    );
}