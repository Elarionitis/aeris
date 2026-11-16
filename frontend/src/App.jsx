import React, { useCallback, useMemo, useState } from 'react';
import { AdvisoryPanel, LanguageSwitch } from './components/AdvisoryPanel';
import { AttributionChart } from './components/AttributionChart';
import { EnforcementQueue } from './components/EnforcementQueue';
import { ForecastChart } from './components/ForecastChart';
import { OrchestratorChat } from './components/OrchestratorChat';
import { StatCards } from './components/StatCards';
import { WardMap } from './components/WardMap';
import { BandPill, ErrorNote, Panel, PanelErrorBoundary } from './components/ui';
import { api } from './lib/api';
import { bandFor, FALLBACK_BANDS } from './lib/aqi';
import { useResource } from './lib/useResource';

const FORECAST_HOURS = 72;
const ENFORCEMENT_LIMIT = 8;
const DEFAULT_LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'kn', name: 'Kannada' },
  { code: 'ta', name: 'Tamil' },
  { code: 'hi', name: 'Hindi' },
];

export default function App() {
  const [selectedWardId, setSelectedWardId] = useState('');
  const [language, setLanguage] = useState('en');

  const meta = useResource((signal) => api.meta(signal), [], { keepPrevious: true });
  const wards = useResource((signal) => api.wards(signal), [], { keepPrevious: true });

  // The band scale and language list come from the API so the dashboard and
  // the backend can never disagree about a band name.
  const bands = meta.data?.band_scale ?? FALLBACK_BANDS;
  const languages = meta.data?.languages ?? DEFAULT_LANGUAGES;
  const wardList = useMemo(() => wards.data ?? [], [wards.data]);

  const activeWardId = selectedWardId || wardList[0]?.ward_id || '';
  const selectedWard = useMemo(
    () => wardList.find((ward) => ward.ward_id === activeWardId),
    [wardList, activeWardId],
  );

  const forecast = useResource(
    (signal) => api.forecast(activeWardId, FORECAST_HOURS, signal),
    [activeWardId],
    { enabled: Boolean(activeWardId) },
  );
  const attribution = useResource(
    (signal) => api.attribution(activeWardId, signal),
    [activeWardId],
    { enabled: Boolean(activeWardId) },
  );
  const advisory = useResource(
    (signal) => api.advisory(activeWardId, language, signal),
    [activeWardId, language],
    { enabled: Boolean(activeWardId) },
  );
  const enforcement = useResource((signal) => api.enforcement(ENFORCEMENT_LIMIT, signal), []);

  const selectWard = useCallback((wardId) => setSelectedWardId(wardId), []);
  const wardBand = selectedWard ? bandFor(selectedWard.aqi, bands) : null;

  return (
    <main className="min-h-screen bg-canvas">
      <header className="border-b border-line px-5 py-6 sm:px-8">
        <div className="mx-auto flex max-w-[1500px] flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-xl font-bold tracking-tight sm:text-2xl">
              Urban Air Quality Intelligence
              <span className="text-accent"> · Bengaluru</span>
            </h1>
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
              Geospatial source attribution, 72-hour hyperlocal forecasting, enforcement
              prioritisation, and multilingual citizen advisories — coordinated by an LLM agent.
            </p>
          </div>
          <p className="max-w-xs rounded-xl border border-edge bg-raised px-3.5 py-2.5 text-xs leading-relaxed text-accent">
            Decision-support only. Validate against municipal data before enforcement action, and
            have advisory translations reviewed before dispatch.
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-[1500px] px-5 py-6 sm:px-8">
        {wards.error ? (
          <div className="mb-6">
            <ErrorNote message={wards.error} onRetry={wards.reload} />
          </div>
        ) : null}

        <div className="flex flex-col gap-5">
          <StatCards
            wards={wardList}
            bands={bands}
            enforcement={enforcement.data}
            forecast={forecast.data}
          />

          <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
            <PanelErrorBoundary title="Ward intelligence map">
              <Panel
                title="Ward intelligence map"
                subtitle="Click a ward to drive every panel below"
                loading={wards.loading && !wardList.length}
                error={wards.error}
                onRetry={wards.reload}
                minHeight={352}
                actions={
                  <label className="flex items-center gap-2 text-xs text-muted">
                    <span className="sr-only sm:not-sr-only">Ward</span>
                    <select
                      aria-label="Select ward"
                      value={activeWardId}
                      onChange={(event) => selectWard(event.target.value)}
                      className="rounded-lg border border-edge bg-raised px-2.5 py-1.5 text-xs text-ink"
                    >
                      {wardList.map((ward) => (
                        <option key={ward.ward_id} value={ward.ward_id}>
                          {ward.ward_name} · {ward.aqi}
                        </option>
                      ))}
                    </select>
                  </label>
                }
              >
                <WardMap
                  wards={wardList}
                  bands={bands}
                  selectedWardId={activeWardId}
                  onSelectWard={selectWard}
                />
                <div className="mt-3 flex flex-wrap gap-2">
                  {bands.map((band) => (
                    <BandPill key={band.label} label={band.label} color={band.color} />
                  ))}
                </div>
              </Panel>
            </PanelErrorBoundary>

            <PanelErrorBoundary title="Ask Aeris">
              <OrchestratorChat
                selectedWardId={activeWardId}
                selectedWardName={selectedWard?.ward_name}
                language={language}
              />
            </PanelErrorBoundary>
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
            <PanelErrorBoundary title="Forecast">
              <Panel
                title={`${selectedWard?.ward_name ?? 'Ward'} — 72-hour AQI forecast`}
                subtitle="Recursive multi-horizon model with confidence bounds"
                loading={forecast.loading}
                error={forecast.error}
                onRetry={forecast.reload}
                minHeight={288}
                actions={
                  wardBand ? <BandPill label={`Now: ${wardBand.label}`} color={wardBand.color} /> : null
                }
              >
                <ForecastChart forecast={forecast.data} bands={bands} />
              </Panel>
            </PanelErrorBoundary>

            <PanelErrorBoundary title="Source attribution">
              <Panel
                title="Source attribution"
                subtitle="Non-negative least squares split of the current reading"
                loading={attribution.loading}
                error={attribution.error}
                onRetry={attribution.reload}
                minHeight={288}
              >
                <AttributionChart attribution={attribution.data} />
              </Panel>
            </PanelErrorBoundary>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <PanelErrorBoundary title="Enforcement priority queue">
              <Panel
                title="Enforcement priority queue"
                subtitle="Severity × controllable share × source density × persistence"
                loading={enforcement.loading}
                error={enforcement.error}
                onRetry={enforcement.reload}
                minHeight={240}
              >
                <EnforcementQueue
                  enforcement={enforcement.data}
                  bands={bands}
                  selectedWardId={activeWardId}
                  onSelectWard={selectWard}
                />
              </Panel>
            </PanelErrorBoundary>

            <PanelErrorBoundary title="Citizen health advisory">
              <Panel
                title={`Citizen health advisory — ${selectedWard?.ward_name ?? 'Ward'}`}
                subtitle="Conservative, vulnerability-weighted guidance"
                loading={advisory.loading}
                error={advisory.error}
                onRetry={advisory.reload}
                minHeight={240}
                actions={
                  <LanguageSwitch languages={languages} value={language} onChange={setLanguage} />
                }
              >
                <AdvisoryPanel advisory={advisory.data} language={language} />
              </Panel>
            </PanelErrorBoundary>
          </div>
        </div>

        <footer className="mt-8 border-t border-line pt-5 text-xs leading-relaxed text-muted">
          {meta.data?.app_name ?? 'AQI Intelligence'} v{meta.data?.version ?? '—'} · forecasting,
          attribution, and enforcement agents orchestrated over a shared ward-time dataset.
        </footer>
      </div>
    </main>
  );
}
