"use client";

import { Field } from "@/components/field";
import { Textarea } from "@/components/ui/textarea";
import { VOICE_PRESETS } from "@/lib/voice";

export function VoiceFields({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="space-y-3">
      <Field
        label="How joel talks"
        hint="Injected into the answer prompt. Leave blank for the default style."
      >
        <Textarea
          value={value}
          placeholder="Short, specific, no preamble…"
          onChange={(e) => onChange(e.target.value)}
        />
      </Field>
      <div className="flex flex-wrap gap-1.5">
        {VOICE_PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className="rounded-full bg-field px-3 py-1 text-[12.5px] font-medium text-ink-2 shadow-hairline hover:bg-hover hover:text-ink"
            onClick={() => onChange(preset.text)}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  );
}
