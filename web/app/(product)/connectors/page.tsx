"use client";

import { IntegrationsPanel } from "@/components/integrations/integrations-panel";
import { PageHeader } from "@/components/page-header";

export default function ConnectorsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <PageHeader
        title="Integrations"
        description="Save a Composio key, then connect a tool. Click a row for scopes, lookback, and sync."
      />
      <IntegrationsPanel surface="connectors" />
    </div>
  );
}
