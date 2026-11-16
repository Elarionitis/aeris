import React from 'react';
import { bandFor, formatNumber, UNHEALTHY_BANDS } from '../lib/aqi';

function StatCard({ label, value, detail, color }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 font-display text-2xl font-bold" style={color ? { color } : undefined}>
        {value}
      </p>
      <p className="mt-0.5 text-xs text-muted">{detail}</p>
    </div>
  );
}

export function StatCards({ wards, bands, enforcement, forecast, engine }) {
  const cityAverage = wards.length
    ? Math.round(wards.reduce((sum, ward) => sum + (ward.aqi || 0), 0) / wards.length)
    : null;
  const cityBand = cityAverage == null ? null : bandFor(cityAverage, bands);
  const unhealthy = wards.filter((ward) => UNHEALTHY_BANDS.has(ward.band)).length;
  const topPriority = enforcement?.items?.[0];
  const peak = forecast?.forecast?.length
    ? forecast.forecast.reduce((best, point) => (point.prediction > best.prediction ? point : best))
    : null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="City average AQI"
        value={cityAverage == null ? '—' : formatNumber(cityAverage)}
        detail={cityBand ? `${cityBand.label} · ${wards.length} wards` : 'awaiting ward data'}
        color={cityBand?.color}
      />
      <StatCard
        label="Wards in Poor or worse"
        value={wards.length ? `${unhealthy} / ${wards.length}` : '—'}
        detail={unhealthy ? 'need active intervention' : 'none above Moderate'}
        color={unhealthy ? '#FF7E00' : '#A3C853'}
      />
      <StatCard
        label="Selected ward 72h peak"
        value={peak ? formatNumber(peak.prediction) : '—'}
        detail={peak ? `expected in ${peak.horizon_hours}h` : 'awaiting forecast'}
        color={peak ? bandFor(peak.prediction, bands).color : undefined}
      />
      <StatCard
        label="Top enforcement priority"
        value={topPriority?.ward_name ?? '—'}
        detail={topPriority ? `score ${formatNumber(topPriority.score)} · ${topPriority.dominant_source}` : 'awaiting queue'}
        color="#F2A65A"
      />
    </div>
  );
}
