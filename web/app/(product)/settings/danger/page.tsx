"use client";

import { AdminOnly } from "@/components/settings/admin-only";
import { DangerPanel } from "@/components/settings/danger-panel";

export default function SettingsDangerPage() {
  return (
    <AdminOnly>
      <DangerPanel />
    </AdminOnly>
  );
}
