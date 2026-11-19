import { Suspense } from "react";
import { BookingClient } from "./BookingClient";

export const revalidate = 0;
export function generateStaticParams() {
  return [];
}

export default function Page() {
  return <Suspense><BookingClient /></Suspense>;
}
