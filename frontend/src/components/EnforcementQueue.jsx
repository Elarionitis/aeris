import React from 'react';
import { bandColor, formatNumber } from '../lib/aqi';

export function EnforcementQueue({ enforcement, bands, selectedWardId, onSelectWard }) {
  const items = enforcement?.items ?? [];
  if (!items.length) {
    return <p className="text-sm text-muted">No wards in the enforcement queue.</p>;
  }
  const topScore = items[0].score || 1;

  return (
    <div>
      <ol className="divide-y divide-line">
        {items.map((item, index) => {
          const isSelected = item.ward_id === selectedWardId;
          return (
            <li key={item.ward_id}>
              <button
                type="button"
                onClick={() => onSelectWard(item.ward_id)}
                aria-current={isSelected ? 'true' : undefined}
                className={`flex w-full items-start gap-3 rounded-lg px-2 py-3 text-left transition-colors hover:bg-raised ${
                  isSelected ? 'bg-raised' : ''
                }`}
              >
                <span className="mt-0.5 font-display text-xs font-bold text-muted">{index + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: bandColor(item.aqi, bands) }}
                      aria-hidden="true"
                    />
                    <span className="truncate text-sm font-semibold">{item.ward_name}</span>
                    <span className="shrink-0 text-xs text-muted">
                      AQI {item.aqi} · {item.aqi_band}
                    </span>
                  </span>
                  <span className="mt-1 block text-xs leading-relaxed text-muted">
                    {item.recommendation}
                  </span>
                  <span className="mt-2 block h-1 overflow-hidden rounded-full bg-line">
                    <span
                      className="block h-full rounded-full bg-accent/70"
                      style={{ width: `${Math.max((item.score / topScore) * 100, 4)}%` }}
                    />
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block font-display text-sm font-bold text-accent">
                    {formatNumber(item.score)}
                  </span>
                  <span className="block text-[11px] text-muted">{item.dominant_source}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className="mt-3 text-xs leading-relaxed text-muted">{enforcement?.disclaimer}</p>
    </div>
  );
}
