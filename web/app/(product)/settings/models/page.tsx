"use client";

import { AdminOnly } from "@/components/settings/admin-only";
import { ModelsPanel } from "@/components/settings/models-panel";

export default function SettingsModelsPage() {
  return (
    <AdminOnly>
      <ModelsPanel />
    </AdminOnly>
  );
}
