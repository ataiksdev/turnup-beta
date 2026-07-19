"use client";
import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { communitiesApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { Users } from "lucide-react";

export default function JoinViaInvitePage() {
  const { token: inviteToken } = useParams<{ token: string }>();
  const router = useRouter();
  const { token } = useAuthStore();

  const joinMutation = useMutation({
    mutationFn: () => communitiesApi.joinViaInvite(token!, inviteToken),
    onSuccess: (community) => router.replace(`/communities/${community.slug}`),
    onError: () => router.replace("/communities"),
  });

  useEffect(() => {
    if (!token) {
      router.replace(`/login?redirect=/communities/join/${inviteToken}`);
      return;
    }
    joinMutation.mutate();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <div className="flex flex-col items-center justify-center h-screen gap-4">
      <div className="w-10 h-10 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      <div className="flex items-center gap-2 text-text-muted text-sm">
        <Users size={16} />
        Joining community…
      </div>
    </div>
  );
}
