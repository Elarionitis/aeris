import React, { useEffect, useMemo, useState } from 'react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

const AQI_BANDS = [
  { max: 50, label: 'Good', color: '#009865' },
  { max: 100, label: 'Satisfactory', color: '#a3c853' },
  { max: 200, label: 'Moderate', color: '#ffd500' },
  { max: 300, label: 'Poor', color: '#ff7e00' },
  { max: 400, label: 'Very Poor', color: '#ff0000' },
  { max: 500, label: 'Severe', color: '#7e0023' },
];

const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'kn', label: 'ಕನ್ನಡ' },
  { code: 'ta', label: 'தமிழ்' },
  { code: 'hi', label: 'हिन्दी' },
];

function bandFor(aqi) {
  return AQI_BANDS.find((band) => aqi <= band.max) || AQI_BANDS[AQI_BANDS.length - 1];
}

function fetchJson(path, signal) {
  return fetch(`${API_BASE}${path}`, { signal }).then(async (response) => {
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  });
}

function showRequestError(error, setError) {
  if (error?.name !== 'AbortError') setError(error.message || 'Failed to load data');
}

class PanelErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card" style={{ padding: 18 }}>
          <div className="display" style={{ fontWeight: 700, marginBottom: 4 }}>{this.props.title}</div>
          <div style={{ color: '#8291AA' }}>This panel failed to render. Other panels remain available.</div>
        </div>
      );
    }
    return this.props.children;
  }
}

function PanelFrame({ title, subtitle, loading, error, right, children }) {
  return (
    <div className="card" style={{ padding: 18 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 10, alignItems: 'flex-start' }}>
        <div>
          <div className="display" style={{ fontWeight: 700, marginBottom: 4 }}>{title}</div>
          {subtitle ? <div style={{ fontSize: 12, color: '#8291AA' }}>{subtitle}</div> : null}
        </div>
        {right}
      </div>
      {loading ? <div style={{ color: '#8291AA', minHeight: 120, display: 'grid', placeItems: 'center' }}>Loading…</div> : error ? <div style={{ color: '#F2A65A', fontSize: 13, lineHeight: 1.6 }}>{error}</div> : children}
    </div>
  );
}

function forecastRows(forecast) {
  return (forecast || []).map((point) => ({
    hour: `T+${point.horizon_hours}h`,
    prediction: point.prediction,
    lower: point.lower,
    upper: point.upper,
  }));
}

function MapFocus({ ward }) {
  const map = useMap();
  useEffect(() => {
    if (ward?.latitude != null && ward?.longitude != null) {
      map.flyTo([ward.latitude, ward.longitude], 14, { duration: 0.7 });
    }
  }, [map, ward?.ward_id]);
  return null;
}

export default function App() {
  const [wards, setWards] = useState([]);
  const [selectedWardId, setSelectedWardId] = useState('');
  const [wardsLoading, setWardsLoading] = useState(true);
  const [wardsError, setWardsError] = useState('');
  const [forecast, setForecast] = useState(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastError, setForecastError] = useState('');
  const [attribution, setAttribution] = useState(null);
  const [attributionLoading, setAttributionLoading] = useState(false);
  const [attributionError, setAttributionError] = useState('');
  const [enforcement, setEnforcement] = useState(null);
  const [enforcementLoading, setEnforcementLoading] = useState(true);
  const [enforcementError, setEnforcementError] = useState('');
  const [lang, setLang] = useState('en');
  const [advisory, setAdvisory] = useState(null);
  const [advisoryLoading, setAdvisoryLoading] = useState(false);
  const [advisoryError, setAdvisoryError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setWardsLoading(true);
    setWardsError('');
    fetchJson('/wards', controller.signal)
      .then((data) => {
        setWards(data);
        setSelectedWardId((current) => current || data?.[0]?.ward_id || '');
      })
      .catch((error) => showRequestError(error, setWardsError))
      .finally(() => setWardsLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedWardId) return;
    const controller = new AbortController();
    setForecastLoading(true);
    setForecastError('');
    fetchJson(`/forecast/${selectedWardId}`, controller.signal)
      .then((data) => setForecast(data))
      .catch((error) => showRequestError(error, setForecastError))
      .finally(() => setForecastLoading(false));
    return () => controller.abort();
  }, [selectedWardId]);

  useEffect(() => {
    if (!selectedWardId) return;
    const controller = new AbortController();
    setAttributionLoading(true);
    setAttributionError('');
    fetchJson(`/attribution/${selectedWardId}`, controller.signal)
      .then((data) => setAttribution(data))
      .catch((error) => showRequestError(error, setAttributionError))
      .finally(() => setAttributionLoading(false));
    return () => controller.abort();
  }, [selectedWardId]);

  useEffect(() => {
    const controller = new AbortController();
    setEnforcementLoading(true);
    setEnforcementError('');
    fetchJson('/enforcement/priority-queue', controller.signal)
      .then((data) => setEnforcement(data))
      .catch((error) => showRequestError(error, setEnforcementError))
      .finally(() => setEnforcementLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedWardId) return;
    const controller = new AbortController();
    setAdvisoryLoading(true);
    setAdvisoryError('');
    fetchJson(`/advisory/${selectedWardId}?lang=${lang}`, controller.signal)
      .then((data) => setAdvisory(data))
      .catch((error) => showRequestError(error, setAdvisoryError))
      .finally(() => setAdvisoryLoading(false));
    return () => controller.abort();
  }, [selectedWardId, lang]);

  const selectedWard = useMemo(() => wards.find((ward) => ward.ward_id === selectedWardId) || wards[0], [wards, selectedWardId]);
  const cityAvg = useMemo(() => Math.round(wards.reduce((sum, ward) => sum + (ward.aqi || 0), 0) / Math.max(wards.length, 1)), [wards]);
  const poorCount = useMemo(() => wards.filter((ward) => (ward.aqi || 0) > 200).length, [wards]);
  const band = bandFor(selectedWard?.aqi || 0);
  const forecastData = useMemo(() => forecastRows(forecast?.forecast), [forecast]);
  const attributionData = useMemo(() => Object.entries(attribution?.breakdown || {}).map(([name, value]) => ({ name: name[0].toUpperCase() + name.slice(1), value })), [attribution]);
  const priorityRows = enforcement?.items || [];

  const wardGeoJson = useMemo(() => ({
    type: 'FeatureCollection',
    features: wards.map((ward) => ({
      type: 'Feature',
      properties: { ward_id: ward.ward_id, ward_name: ward.ward_name, aqi: ward.aqi, band: ward.band },
      geometry: ward.geometry,
    })),
  }), [wards]);

  function styleFeature(feature) {
    const color = bandFor(feature?.properties?.aqi || 0).color;
    return {
      color,
      weight: feature?.properties?.ward_id === selectedWardId ? 3 : 1.2,
      fillColor: color,
      fillOpacity: 0.35,
    };
  }

  function onEachFeature(feature, layer) {
    layer.on({ click: () => setSelectedWardId(feature.properties.ward_id) });
    if (layer.bindTooltip) {
      layer.bindTooltip(`${feature.properties.ward_name} · AQI ${feature.properties.aqi}`, { sticky: true });
    }
  }

  return (
    <main style={{ minHeight: '100vh', background: '#0B1220', color: '#E8EDF5', fontFamily: 'Inter, sans-serif' }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600&display=swap');
        .display { font-family: 'Space Grotesk', sans-serif; }
        .card { background: #131B2E; border: 1px solid #223047; border-radius: 14px; }
      `}</style>

      <div style={{ padding: '28px 32px 12px', borderBottom: '1px solid #1B2436' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div className="display" style={{ fontSize: 26, fontWeight: 700, letterSpacing: 0.3 }}>
              Urban Air Quality Intelligence <span style={{ color: '#F2A65A' }}>· Bengaluru</span>
            </div>
            <div style={{ color: '#8291AA', fontSize: 13, marginTop: 4 }}>
              Geospatial source attribution · 72h hyperlocal forecast · enforcement prioritisation · multilingual citizen advisory
            </div>
          </div>
          <div style={{ background: '#1B2436', border: '1px solid #2A3855', borderRadius: 10, padding: '8px 14px', fontSize: 12, color: '#F2A65A' }}>
            ⚠ Live data from API responses; translations must be reviewed by a native speaker before dispatch
          </div>
        </div>
      </div>

      <div style={{ padding: 28, display: 'grid', gap: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 16 }}>
          {[
            { label: 'City Avg AQI (now)', value: cityAvg || '—', sub: band.label, color: band.color },
            { label: 'Wards in Poor/Worse', value: `${poorCount} / ${Math.max(wards.length, 1)}`, sub: 'need active intervention', color: '#ff7e00' },
            { label: 'Forecast Confidence', value: forecast?.forecast?.length ? 'Live' : '—', sub: 'api-backed 72h curve', color: '#4ADE80' },
            { label: 'Top Enforcement Priority', value: priorityRows[0]?.ward_name || '—', sub: `score ${priorityRows[0]?.score ?? '—'}`, color: '#F2A65A' },
          ].map((item) => (
            <div key={item.label} className="card" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: '#8291AA' }}>{item.label}</div>
              <div className="display" style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: item.color }}>{item.value}</div>
              <div style={{ fontSize: 12, color: '#8291AA', marginTop: 2 }}>{item.sub}</div>
            </div>
          ))}
        </div>

        <PanelErrorBoundary title="Ward Intelligence">
          <div className="card" style={{ padding: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
              <div className="display" style={{ fontSize: 15, fontWeight: 700, color: '#8291AA' }}>WARD INTELLIGENCE MAP</div>
              <label style={{ fontSize: 12, color: '#8291AA' }}>
                Select ward{' '}
                <select
                  aria-label="Select ward"
                  value={selectedWardId}
                  onChange={(event) => setSelectedWardId(event.target.value)}
                  style={{ marginLeft: 6, background: '#1B2436', color: '#E8EDF5', border: '1px solid #2A3855', borderRadius: 6, padding: '6px 8px' }}
                >
                  {wards.map((ward) => <option key={ward.ward_id} value={ward.ward_id}>{ward.ward_name}</option>)}
                </select>
              </label>
            </div>
            {wardsLoading ? (
              <div style={{ color: '#8291AA', minHeight: 360, display: 'grid', placeItems: 'center' }}>Loading wards…</div>
            ) : wardsError ? (
              <div style={{ color: '#F2A65A' }}>{wardsError}</div>
            ) : (
              <div style={{ height: 420, borderRadius: 12, overflow: 'hidden' }}>
                <MapContainer center={[12.9716, 77.5946]} zoom={11} style={{ height: '100%', width: '100%' }}>
                  <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  <MapFocus ward={selectedWard} />
                  <GeoJSON data={wardGeoJson} style={styleFeature} onEachFeature={onEachFeature} />
                </MapContainer>
              </div>
            )}
          </div>
        </PanelErrorBoundary>

        <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 0.9fr', gap: 16 }}>
          <PanelErrorBoundary title="Forecast">
            <PanelFrame title={`${selectedWard?.ward_name || 'Ward'} — 72h AQI Forecast`} subtitle="API-backed forecast with confidence bounds" loading={forecastLoading} error={forecastError} right={<div className="card" style={{ background: '#1B2436', borderColor: '#2A3855', borderRadius: 999, padding: '6px 12px', fontSize: 12 }}>Selected: {selectedWard?.band || '—'}</div>}>
              <div style={{ height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={forecastData}>
                    <CartesianGrid stroke="#1B2436" />
                    <XAxis dataKey="hour" tick={{ fontSize: 10, fill: '#8291AA' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#8291AA' }} />
                    <Tooltip contentStyle={{ background: '#131B2E', border: '1px solid #223047' }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="prediction" stroke="#F2A65A" strokeWidth={2.5} dot={false} name="Forecast" />
                    <Line type="monotone" dataKey="lower" stroke="#556080" strokeWidth={1.2} strokeDasharray="4 4" dot={false} name="Lower CI" />
                    <Line type="monotone" dataKey="upper" stroke="#556080" strokeWidth={1.2} strokeDasharray="4 4" dot={false} name="Upper CI" />
                    <Area type="monotone" dataKey="prediction" stroke="#F2A65A" fill="#F2A65A" fillOpacity={0.05} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </PanelFrame>
          </PanelErrorBoundary>

          <PanelErrorBoundary title="Attribution">
            <PanelFrame title="Source Attribution" subtitle="Live contribution breakdown from attribution endpoint" loading={attributionLoading} error={attributionError}>
              <div style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={attributionData} layout="vertical" margin={{ left: 20, right: 48 }}>
                    <CartesianGrid stroke="#1B2436" />
                    <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10, fill: '#8291AA' }} tickFormatter={(value) => `${value}%`} />
                    <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#E8EDF5' }} width={90} />
                    <Tooltip contentStyle={{ background: '#131B2E', border: '1px solid #223047' }} />
                    <Bar dataKey="value" fill="#F2A65A" radius={[0, 6, 6, 0]}>
                      <LabelList dataKey="value" position="right" fill="#E8EDF5" fontSize={12} formatter={(value) => `${Number(value).toFixed(1)}%`} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
                {attributionData.map((item) => (
                  <div key={item.name} className="card" style={{ background: '#1B2436', borderColor: '#2A3855', padding: '6px 9px', fontSize: 12 }}>
                    {item.name}: <strong style={{ color: '#F2A65A' }}>{Number(item.value).toFixed(1)}%</strong>
                  </div>
                ))}
              </div>
              <div style={{ fontSize: 12, color: '#8291AA', marginTop: 6 }}>Confidence score: {attribution?.confidence_score ?? '—'}</div>
            </PanelFrame>
          </PanelErrorBoundary>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <PanelErrorBoundary title="Enforcement Priority">
            <PanelFrame title="Enforcement Priority Queue" subtitle="Top 10 wards by score" loading={enforcementLoading} error={enforcementError}>
              <div style={{ display: 'grid', gap: 8 }}>
                {priorityRows.map((item, index) => (
                  <button
                    key={item.ward_id}
                    type="button"
                    onClick={() => setSelectedWardId(item.ward_id)}
                    aria-pressed={item.ward_id === selectedWardId}
                    style={{ display: 'flex', width: '100%', justifyContent: 'space-between', padding: '8px 0', border: 'none', borderBottom: index < priorityRows.length - 1 ? '1px solid #1B2436' : 'none', gap: 8, background: item.ward_id === selectedWardId ? '#1B2436' : 'transparent', color: '#E8EDF5', textAlign: 'left', cursor: 'pointer', borderRadius: 6 }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{index + 1}. {item.ward_name}</div>
                      <div style={{ fontSize: 11, color: '#8291AA' }}>{item.recommendation}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div className="display" style={{ color: '#F2A65A', fontWeight: 700 }}>{item.score}</div>
                      <div style={{ fontSize: 11, color: '#8291AA' }}>{item.dominant_source}</div>
                    </div>
                  </button>
                ))}
              </div>
            </PanelFrame>
          </PanelErrorBoundary>

          <PanelErrorBoundary title="Citizen Advisory">
            <PanelFrame
              title={`Citizen Health Advisory — ${selectedWard?.ward_name || 'Ward'}`}
              subtitle="Live advisory text from backend LLM cache"
              loading={advisoryLoading}
              error={advisoryError}
              right={
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {LANGS.map((item) => (
                    <button
                      key={item.code}
                      onClick={() => setLang(item.code)}
                      style={{
                        fontSize: 11,
                        padding: '4px 8px',
                        borderRadius: 6,
                        cursor: 'pointer',
                        background: lang === item.code ? '#F2A65A' : '#1B2436',
                        color: lang === item.code ? '#0B1220' : '#E8EDF5',
                        border: '1px solid #2A3855',
                      }}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              }
            >
              <div style={{ fontSize: 13.5, lineHeight: 1.6, color: '#E8EDF5' }}>{advisory?.advisory || 'No advisory available yet.'}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,minmax(0,1fr))', gap: 8, marginTop: 12, fontSize: 12 }}>
                <div className="card" style={{ background: '#1B2436', borderColor: '#2A3855', padding: 10 }}>Near school: {String(advisory?.vulnerability_flags?.near_school ?? false)}</div>
                <div className="card" style={{ background: '#1B2436', borderColor: '#2A3855', padding: 10 }}>Near hospital: {String(advisory?.vulnerability_flags?.near_hospital ?? false)}</div>
                <div className="card" style={{ background: '#1B2436', borderColor: '#2A3855', padding: 10 }}>Elderly high: {String(advisory?.vulnerability_flags?.elderly_population_high ?? false)}</div>
              </div>
              <div style={{ fontSize: 11, color: '#8291AA', marginTop: 10 }}>Delivery channels: {(advisory?.delivery_channels || []).join(', ') || '—'}</div>
              <div style={{ fontSize: 11, color: '#8291AA', marginTop: 6 }}>{advisory?.disclaimer || 'Translations should be reviewed by a native speaker before real-world dispatch.'}</div>
            </PanelFrame>
          </PanelErrorBoundary>
        </div>
      </div>
    </main>
  );
}
