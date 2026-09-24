import React from 'react';
import Sidebar from './Sidebar';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex h-screen bg-background overflow-hidden">
      {/* Ambient glow blobs — echo the hero's sun */}
      <div aria-hidden className="glow-teal  -top-40 -left-32 w-[36rem] h-[36rem]" />
      <div aria-hidden className="glow-amber -bottom-40 -right-32 w-[32rem] h-[32rem]" />

      {/* Grid overlay */}
      <div aria-hidden className="absolute inset-0 bg-grid-pattern opacity-60 pointer-events-none" />

      <Sidebar />
      <main className="relative flex-1 flex flex-col overflow-hidden min-w-0">
        {children}
      </main>
    </div>
  );
}