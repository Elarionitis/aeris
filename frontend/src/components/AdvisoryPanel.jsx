import React from 'react';
import { LANGUAGE_LABELS } from '../lib/aqi';

const FLAG_LABELS = {
  near_school: 'Near schools',
  near_hospital: 'Near hospitals',
  elderly_population_high: 'High elderly share',
};

export function LanguageSwitch({ languages, value, onChange }) {
  return (
    <div className="flex flex-wrap justify-end gap-1.5" role="group" aria-label="Advisory language">
      {languages.map((language) => {
        const active = language.code === value;
        return (
          <button
            key={language.code}
            type="button"
            onClick={() => onChange(language.code)}
            aria-pressed={active}
            lang={language.code}
            className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
              active
                ? 'border-accent bg-accent text-canvas'
                : 'border-edge bg-raised text-ink hover:bg-line'
            }`}
          >
            {LANGUAGE_LABELS[language.code] ?? language.name}
          </button>
        );
      })}
    </div>
  );
}

export function AdvisoryPanel({ advisory, language }) {
  if (!advisory) {
    return <p className="text-sm text-muted">No advisory available for this ward yet.</p>;
  }
  const flags = advisory.vulnerability_flags ?? {};
  const index = Number(advisory.vulnerability_index ?? 0);

  return (
    <div>
      <blockquote
        lang={language}
        className="rounded-xl border-l-2 border-accent bg-raised/60 p-4 text-[15px] leading-relaxed"
      >
        {advisory.advisory}
      </blockquote>

      <div className="mt-4 flex items-center justify-between text-xs text-muted">
        <span>Population vulnerability index</span>
        <span className="font-semibold text-ink">{index.toFixed(2)} / 1.00</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-raised">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${Math.min(Math.max(index, 0), 1) * 100}%` }}
        />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {Object.entries(FLAG_LABELS).map(([key, label]) => (
          <span
            key={key}
            className={`chip ${flags[key] ? 'border-accent/60 text-accent' : 'text-muted'}`}
          >
            {flags[key] ? '●' : '○'} {label}
          </span>
        ))}
      </div>

      <dl className="mt-4 space-y-1 text-xs text-muted">
        <div className="flex gap-2">
          <dt className="shrink-0">Delivery channels:</dt>
          <dd className="text-ink">{(advisory.delivery_channels ?? []).join(', ') || '—'}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="shrink-0">Written by:</dt>
          <dd className="text-ink">
            {advisory.advisory_source === 'llm' ? 'LLM, safety-filtered' : 'reviewed template'}
          </dd>
        </div>
      </dl>

      <p className="mt-3 text-xs leading-relaxed text-muted">{advisory.disclaimer}</p>
    </div>
  );
}
