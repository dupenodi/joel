"use client";

import { AdminOnly } from "@/components/settings/admin-only";
import { SlackPanel } from "@/components/settings/slack-panel";

export default function SettingsSlackPage() {
  return (
    <AdminOnly>
      <SlackPanel />
    </AdminOnly>
  );
}
