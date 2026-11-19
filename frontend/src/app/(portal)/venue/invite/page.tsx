"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiErrorMessage } from "@/lib/api";
import { portalApi } from "@/lib/marketplace";
import { useAuthStore } from "@/store/auth";

function Accept() {
  const token = useSearchParams().get("token") ?? "";
  const { token: auth } = useAuthStore();
  const router = useRouter();
  const [msg, setMsg] = useState("Joining the venue team…");
  useEffect(() => {
    if (!auth || !token) return;
    portalApi.acceptInvite(auth, token)
      .then((r) => router.replace(`/venue/manage?id=${r.venue_id}`))
      .catch((e) => setMsg(apiErrorMessage(e, "This invitation couldn't be accepted.")));
  }, [auth, token]); // eslint-disable-line react-hooks/exhaustive-deps
  return <p className="text-sm text-text text-center py-16">{msg}</p>;
}

export default function InvitePage() {
  return <Suspense><Accept /></Suspense>;
}
