"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** My Tickets is now part of My Vibes (a ticket's own page, with its QR code, is unchanged). */
export default function Page() {
  const router = useRouter();
  useEffect(() => { router.replace("/vibes"); }, [router]);
  return null;
}
