import { Suspense } from "react";
import TicketDetailPageClient from "./TicketDetailPageClient";

export const revalidate = 0;
export function generateStaticParams() { return []; }

export default function Page() {
  return <Suspense><TicketDetailPageClient /></Suspense>;
}
