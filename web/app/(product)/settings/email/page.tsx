"use client";

import { AdminOnly } from "@/components/settings/admin-only";
import { EmailPanel } from "@/components/settings/email-panel";

export default function SettingsEmailPage() {
  return (
    <AdminOnly>
      <EmailPanel />
    </AdminOnly>
  );
}
