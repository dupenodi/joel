"use client";

import { Button } from "@/components/beautifului/primitives/button";
import { Field } from "@/components/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { researchWorkspaceWebsite, type WorkspaceResearchResult } from "@/lib/api";
import { useState } from "react";

export function CompanyAboutFields({
  websiteUrl,
  onWebsiteUrl,
  about,
  onAbout,
  researchAllowed = true,
  autoFocusAbout = false,
  onResearched,
}: {
  websiteUrl: string;
  onWebsiteUrl: (value: string) => void;
  about: string;
  onAbout: (value: string) => void;
  researchAllowed?: boolean;
  autoFocusAbout?: boolean;
  onResearched?: (result: WorkspaceResearchResult) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sources, setSources] = useState<{ url: string; title: string }[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);

  return (
    <div className="space-y-3">
      <Field
        label="Website"
        hint={
          researchAllowed
            ? "We'll pull same-site pages (home, llms.txt, docs links) into About. No LLM."
            : "Website research is disabled on this install (JOEL_ALLOW_WEB_FETCH=0)."
        }
      >
        <div className="flex gap-2">
          <Input
            className="min-w-0 flex-1"
            placeholder="https://hydradb.com"
            value={websiteUrl}
            onChange={(e) => {
              onWebsiteUrl(e.target.value);
              setError(null);
            }}
          />
          {researchAllowed && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              loading={busy}
              disabled={!websiteUrl.trim()}
              onClick={() => {
                setBusy(true);
                setError(null);
                setWarnings([]);
                void researchWorkspaceWebsite(websiteUrl.trim())
                  .then((res) => {
                    onAbout(res.about);
                    setSources(
                      res.sources.map((s) => ({
                        url: s.url,
                        title: s.title,
                      })),
                    );
                    setWarnings(res.warnings ?? []);
                    onResearched?.(res);
                  })
                  .catch((err: unknown) => {
                    setError(
                      err instanceof Error
                        ? err.message
                        : "Could not research that site",
                    );
                  })
                  .finally(() => setBusy(false));
              }}
            >
              Research
            </Button>
          )}
        </div>
      </Field>
      <Field
        label="About"
        hint="Editable. Saved into joel's answer prompt so Chat works before connectors finish."
      >
        <Textarea
          autoFocus={autoFocusAbout}
          value={about}
          placeholder="We build …"
          onChange={(e) => onAbout(e.target.value)}
          className="min-h-[160px]"
        />
      </Field>
      {sources.length > 0 && (
        <p className="text-[12px] leading-relaxed text-ink-3">
          From {sources.length} page{sources.length === 1 ? "" : "s"}
          {sources.slice(0, 4).map((s) => (
            <span key={s.url}>
              {" · "}
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="underline-offset-2 hover:underline"
              >
                {s.title || s.url}
              </a>
            </span>
          ))}
          {sources.length > 4 ? " · …" : ""}
        </p>
      )}
      {warnings.length > 0 && (
        <p className="text-[12px] text-ink-3">{warnings[0]}</p>
      )}
      {error && <p className="text-[12.5px] text-red">{error}</p>}
    </div>
  );
}
