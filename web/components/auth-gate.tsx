"use client";

import { getAuthStatus } from "@/lib/api";
import { authDestination } from "@/lib/auth";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { OnboardingSkeleton } from "@/components/skeletons";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ok, setOk] = useState(false);

  useEffect(() => {
    let alive = true;
    void getAuthStatus()
      .then((status) => {
        if (!alive) return;
        const dest = authDestination(status, pathname || "/");
        if (dest) {
          router.replace(dest);
          return;
        }
        setOk(true);
      })
      .catch(() => {
        if (!alive) return;
        router.replace("/login");
      });
    return () => {
      alive = false;
    };
  }, [pathname, router]);

  if (!ok) return <OnboardingSkeleton />;
  return <>{children}</>;
}
