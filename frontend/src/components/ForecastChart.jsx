import React, { useMemo } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { bandFor, formatNumber } from '../lib/aqi';

const AXIS = { fontSize: 11, fill: '#8291AA' };
const TOOLTIP_STYLE = {
  background: '#131B2E',
  border: '1px solid #2A3855',
  borderRadius: 10,
  fontSize: 12,
};

export function ForecastChart({ forecast, bands }) {
  const data = useMemo(
    () =>
      (forecast?.forecast ?? []).map((point) => ({
        hour: point.horizon_hours,
        label: `T+${point.horizon_hours}h`,
        prediction: point.prediction,
        // Recharts stacks an area from a [low, high] pair, which draws the
        // confidence band in one shape instead of two dashed lines.
        interval: [point.lower, point.upper],
      })),
    [forecast],
  );

  if (!data.length) {
    return <p className="text-sm text-muted">No forecast points returned for this ward.</p>;
  }

  const peak = data.reduce((best, point) => (point.prediction > best.prediction ? point : best));
  const peakBand = bandFor(peak.prediction, bands);

  return (
    <div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="#1B2436" vertical={false} />
            <XAxis
              dataKey="hour"
              tick={AXIS}
              tickFormatter={(hour) => `${hour}h`}
              interval={Math.max(Math.floor(data.length / 8) - 1, 0)}
            />
            <YAxis
              tick={AXIS}
              width={44}
              tickFormatter={(value) => Math.round(value)}
              domain={[
                (dataMin) => Math.max(Math.floor((dataMin - 15) / 25) * 25, 0),
                (dataMax) => Math.ceil((dataMax + 15) / 25) * 25,
              ]}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              labelFormatter={(hour) => `${hour} hours ahead`}
              formatter={(value, name) =>
                Array.isArray(value)
                  ? [`${formatNumber(value[0])} – ${formatNumber(value[1])}`, 'Confidence range']
                  : [formatNumber(value, 1), name]
              }
            />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
            <Area
              dataKey="interval"
              name="Confidence range"
              stroke="none"
              fill="#F2A65A"
              fillOpacity={0.14}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="prediction"
              name="Forecast AQI"
              stroke="#F2A65A"
              strokeWidth={2.5}
              dot={false}
            />
            <ReferenceLine
              y={peak.prediction}
              stroke={peakBand.color}
              strokeDasharray="4 4"
              strokeOpacity={0.7}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-3 text-xs text-muted">
        Peak AQI <span className="font-semibold text-ink">{formatNumber(peak.prediction, 1)}</span> (
        {peakBand.label}) expected {peak.hour}h out. Seeded from{' '}
        {forecast.source === 'baseline_history' ? 'service ward history' : 'the supplied history'}.
      </p>
    </div>
  );
}
