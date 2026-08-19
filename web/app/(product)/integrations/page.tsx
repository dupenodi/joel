"use client";

import { ContentFrame } from "@/components/app-frame";
import { PauseToggle } from "@/components/install-panel";
import { IntegrationsPanel } from "@/components/integrations/integrations-panel";
import { PageHeader } from "@/components/page-header";

export default function IntegrationsPage() {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto py-8">
      <ContentFrame width="wide">
        <PageHeader
          title="Integrations"
          description="Click a tool to connect it."
          actions={<PauseToggle />}
        />
        <IntegrationsPanel surface="integrations" />
      </ContentFrame>
    </div>
  );
}
