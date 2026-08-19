"use client";

import { ContentFrame } from "@/components/app-frame";
import { InstallPanel } from "@/components/install-panel";
import { PageHeader } from "@/components/page-header";
import { WorkspacePanel } from "@/components/workspace-panel";

export default function SettingsPage() {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto py-8">
      <ContentFrame>
        <PageHeader
          title="Workspace"
          description="People, models, and wipe. Tools stay on Integrations."
        />
        <div className="space-y-8">
          <WorkspacePanel />
          <InstallPanel />
        </div>
      </ContentFrame>
    </div>
  );
}
