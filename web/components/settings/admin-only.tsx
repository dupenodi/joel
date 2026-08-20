"use client";

import { getWorkspace } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SettingsSkeleton } from "@/components/skeletons";

/** Redirect non-admins away from admin-only settings sections. */
export function AdminOnly({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ok, setOk] = useState(false);

  useEffect(() => {
    void getWorkspace()
      .then((data) => {
        if (data.me.role !== "admin" && data.me.role !== "owner" && !data.me.is_admin) {
          router.replace("/settings/general");
          return;
        }
        setOk(true);
      })
      .catch(() => router.replace("/settings/general"));
  }, [router]);

  if (!ok) return <SettingsSkeleton />;
  return <>{children}</>;
}
