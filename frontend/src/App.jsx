import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const chartData = [
  { time: '06:00', now: 82, forecast: 88 },
  { time: '09:00', now: 91, forecast: 95 },
  { time: '12:00', now: 104, forecast: 101 },
  { time: '15:00', now: 118, forecast: 112 },
  { time: '18:00', now: 109, forecast: 106 },
  { time: '21:00', now: 96, forecast: 94 },
];

const sources = [
  { label: 'Live feeds', value: '3 sources', tone: 'signal', barClassName: 'bg-signal' },
  { label: 'Forecast horizon', value: '48 hours', tone: 'amber', barClassName: 'bg-amber' },
  { label: 'Alert confidence', value: 'High', tone: 'alert', barClassName: 'bg-alert' },
];

export default function App() {
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.16),_transparent_30%),linear-gradient(180deg,_#f8fafc_0%,_#e2e8f0_100%)] text-ink">
      <section className="mx-auto flex min-h-screen max-w-7xl flex-col gap-8 px-6 py-10 lg:px-10">
        <header className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/80 p-6 shadow-glow backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-signal">AQI Intelligence</p>
              <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-5xl">Air quality analysis built for fast calls.</h1>
            </div>
            <div className="rounded-2xl bg-ink px-4 py-3 text-right text-white">
              <p className="text-xs uppercase tracking-[0.24em] text-mist/70">Current AQI</p>
              <p className="text-3xl font-semibold">104</p>
              <p className="text-sm text-mist/80">Moderate, trending up</p>
            </div>
          </div>
          <p className="max-w-3xl text-base leading-7 text-slate-600">
            A decision layer for city-level AQI monitoring, forecasting, and attribution. The backend will ingest external sources, while the frontend tracks live and predicted trends in one view.
          </p>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          {sources.map((item) => (
            <article key={item.label} className="rounded-2xl border border-white/70 bg-white/80 p-5 shadow-glow backdrop-blur">
              <p className="text-sm font-medium text-slate-500">{item.label}</p>
              <p className="mt-2 text-2xl font-semibold text-ink">{item.value}</p>
              <div className={`mt-4 h-1.5 w-20 rounded-full ${item.barClassName}`} />
            </article>
          ))}
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.4fr_0.9fr]">
          <article className="rounded-3xl border border-white/70 bg-white/90 p-6 shadow-glow backdrop-blur">
            <div className="mb-6 flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">Trend view</p>
                <h2 className="mt-1 text-2xl font-semibold">Observed vs forecast AQI</h2>
              </div>
              <div className="rounded-full bg-slate-100 px-4 py-2 text-sm text-slate-600">Updated 5 min ago</div>
            </div>
            <div className="h-96 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="nowFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="forecastFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="4 4" stroke="#e2e8f0" />
                  <XAxis dataKey="time" stroke="#64748b" />
                  <YAxis stroke="#64748b" />
                  <Tooltip />
                  <Legend />
                  <Area type="monotone" dataKey="now" name="Observed" stroke="#14b8a6" fill="url(#nowFill)" strokeWidth={2.5} />
                  <Area type="monotone" dataKey="forecast" name="Forecast" stroke="#f59e0b" fill="url(#forecastFill)" strokeWidth={2.5} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </article>

          <aside className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-ink p-6 text-white shadow-glow">
            <div>
              <p className="text-sm uppercase tracking-[0.24em] text-mist/70">System status</p>
              <h2 className="mt-2 text-2xl font-semibold">Backend ready for local development</h2>
            </div>
            <div className="grid gap-3 text-sm text-mist/85">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">CORS enabled for Vite on localhost:5173</div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">API routes reserved for ingestion, attribution, and forecasting</div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">Docker compose will run both services together</div>
            </div>
          </aside>
        </section>
      </section>
    </main>
  );
}
