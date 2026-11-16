/**
 * CPCB National AQI bands.
 *
 * These mirror the backend's app/core/aqi.py and act as a fallback until
 * /meta responds, so the UI and the API never disagree about a band name.
 */
export const FALLBACK_BANDS = [
  { label: 'Good', lower: 0, upper: 50, color: '#009865' },
  { label: 'Satisfactory', lower: 51, upper: 100, color: '#A3C853' },
  { label: 'Moderate', lower: 101, upper: 200, color: '#FFD500' },
  { label: 'Poor', lower: 201, upper: 300, color: '#FF7E00' },
  { label: 'Very Poor', lower: 301, upper: 400, color: '#FF0000' },
  { label: 'Severe', lower: 401, upper: null, color: '#7E0023' },
];

/** Bands at or above which enforcement and health messaging escalate. */
export const UNHEALTHY_BANDS = new Set(['Poor', 'Very Poor', 'Severe']);

export function bandFor(aqi, bands = FALLBACK_BANDS) {
  const value = Math.max(Number(aqi) || 0, 0);
  return bands.find((band) => band.upper == null || value <= band.upper) ?? bands[bands.length - 1];
}

export function bandColor(aqi, bands) {
  return bandFor(aqi, bands).color;
}

export const LANGUAGE_LABELS = {
  en: 'English',
  kn: 'ಕನ್ನಡ',
  ta: 'தமிழ்',
  hi: 'हिन्दी',
};

export function formatNumber(value, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
