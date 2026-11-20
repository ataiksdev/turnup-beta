"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";
import { ThemeController } from "@/components/layout/ThemeController";
import { OfflineBanner } from "@/components/layout/OfflineBanner";
import { OfflineSync } from "@/components/layout/OfflineSync";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 1000 * 60,     // 1 min
            gcTime: 1000 * 60 * 10,   // 10 min
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeController />
      {children}
      <OfflineBanner />
      <OfflineSync />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
