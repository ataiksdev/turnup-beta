"use client";
import { useAuthStore } from "@/store/auth";
import { redirect } from "next/navigation";
import { useEffect } from "react";

// Redirect /profile → /profile/:username
export default function ProfileRedirect() {
  const { user } = useAuthStore();

  useEffect(() => {
    if (user?.username) {
      redirect(`/profile/${user.username}`);
    } else {
      redirect("/login");
    }
  }, [user]);

  return null;
}
