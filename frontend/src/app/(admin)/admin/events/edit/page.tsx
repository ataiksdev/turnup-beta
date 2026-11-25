"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AdminEventForm } from "@/components/admin/AdminEventForm";

// The id comes from the query string (?id=...) so this page also works in the static
// (Capacitor) build, like the other admin detail pages.
function EditForm() {
  const id = useSearchParams().get("id") ?? "";
  return <AdminEventForm key={id} eventId={id} />;
}

export default function AdminEditEventPage() {
  return <Suspense><EditForm /></Suspense>;
}
