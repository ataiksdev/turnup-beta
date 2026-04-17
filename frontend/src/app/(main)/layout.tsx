import { BottomNav } from "@/components/layout/BottomNav";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen pb-24">
      {/* id targets the SkipNav link */}
      <main id="main-content" tabIndex={-1} className="outline-none">
        {children}
      </main>
      <BottomNav />
    </div>
  );
}
