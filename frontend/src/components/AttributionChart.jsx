import React, { useMemo } from 'react';
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts';

const SOURCE_COLORS = {
  Traffic: '#F2A65A',
  Construction: '#7DD3FC',
  Industrial: '#F87171',
  Other: '#A3A3C2',
};

const SOURCE_ORDER = ['Traffic', 'Construction', 'Industrial', 'Other'];

function titleCase(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function AttributionChart({ attribution }) {
  const data = useMemo(() => {
    const breakdown = attribution?.breakdown ?? {};
    return SOURCE_ORDER.filter((name) => breakdown[name.toLowerCase()] != null).map((name) => ({
      name,
      value: Number(breakdown[name.toLowerCase()]),
    }));
  }, [attribution]);

  if (!data.length) {
    return <p className="text-sm text-muted">No attribution breakdown available for this ward.</p>;
  }

  const dominant = data.reduce((best, item) => (item.value > best.value ? item : best));
  const confidence = Number(attribution?.confidence_score ?? 0);

  return (
    <div>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 0, right: 56, top: 0, bottom: 0 }}>
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis
              dataKey="name"
              type="category"
              tick={{ fontSize: 12, fill: '#E8EDF5' }}
              width={92}
              axisLine={false}
              tickLine={false}
            />
            <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={22} isAnimationActive={false}>
              {data.map((item) => (
                <Cell key={item.name} fill={SOURCE_COLORS[item.name]} />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                fill="#E8EDF5"
                fontSize={12}
                formatter={(value) => `${Number(value).toFixed(1)}%`}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-2 text-sm">
        Dominant source:{' '}
        <span className="font-semibold" style={{ color: SOURCE_COLORS[dominant.name] }}>
          {dominant.name} ({dominant.value.toFixed(1)}%)
        </span>
      </p>

      <div className="mt-3">
        <div className="flex items-center justify-between text-xs text-muted">
          <span>Model confidence (R²)</span>
          <span className="font-semibold text-ink">{confidence.toFixed(2)}</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-raised">
          <div
            className="h-full rounded-full bg-accent"
            style={{ width: `${Math.min(Math.max(confidence, 0), 1) * 100}%` }}
          />
        </div>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-muted">
        {titleCase(attribution?.method?.replace(/_/g, ' ') ?? 'model')} over source-activity proxies,
        not stack-level measurement.
      </p>
    </div>
  );
}
