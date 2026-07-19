import EventAnalyticsPageClient from "./EventAnalyticsPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <EventAnalyticsPageClient />;
}
