import React, { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { useResource } from '../lib/useResource';

const AGENT_STYLES = {
  forecasting: { label: 'Forecasting agent', color: '#F2A65A' },
  attribution: { label: 'Attribution agent', color: '#F87171' },
  enforcement: { label: 'Enforcement agent', color: '#7DD3FC' },
  registry: { label: 'Ward registry', color: '#A3C853' },
  unknown: { label: 'Agent', color: '#8291AA' },
};

const SUGGESTIONS = [
  'Why is BTM polluted and will it get worse?',
  'Where should enforcement teams go first?',
  'What is the 72-hour outlook for HSR Layout?',
  'Give me a city-wide air quality overview',
];

let messageId = 0;
const nextId = () => `message-${(messageId += 1)}`;

function AgentChip({ entry }) {
  const style = AGENT_STYLES[entry.agent] ?? AGENT_STYLES.unknown;
  const failed = entry.ok === false;
  return (
    <span
      className="chip"
      style={{ borderColor: failed ? '#F87171' : `${style.color}66` }}
      title={`${entry.tool}(${Object.entries(entry.arguments ?? {})
        .map(([key, value]) => `${key}=${value}`)
        .join(', ')})`}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: failed ? '#F87171' : style.color }}
        aria-hidden="true"
      />
      {style.label}
      {failed ? ' · no data' : ''}
    </span>
  );
}

function Message({ message }) {
  if (message.role === 'user') {
    return (
      <li className="flex animate-fade-up justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2.5 text-sm text-canvas">
          {message.text}
        </p>
      </li>
    );
  }

  return (
    <li className="animate-fade-up">
      {message.trace?.length ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {message.trace.map((entry, index) => (
            <AgentChip key={`${entry.tool}-${index}`} entry={entry} />
          ))}
        </div>
      ) : null}
      <div
        className={`max-w-[92%] rounded-2xl rounded-bl-md border px-3.5 py-2.5 text-sm leading-relaxed ${
          message.failed ? 'border-accent/40 bg-accent/5 text-accent' : 'border-line bg-raised'
        }`}
      >
        {message.text}
      </div>
      {message.engine ? (
        <p className="mt-1.5 text-[11px] text-muted">
          {message.engine === 'langgraph'
            ? `LangGraph · ${message.llm?.provider ?? 'llm'}`
            : 'Deterministic routing · no LLM key configured'}
          {message.elapsedMs != null ? ` · ${message.elapsedMs}ms` : ''}
        </p>
      ) : null}
    </li>
  );
}

export function OrchestratorChat({ selectedWardId, selectedWardName, language }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [pending, setPending] = useState(false);
  const listRef = useRef(null);

  const { data: catalogue } = useResource((signal) => api.agentTools(signal), [], {
    keepPrevious: true,
  });

  useEffect(() => {
    // Keep the newest turn in view as the conversation grows.
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, pending]);

  async function ask(text) {
    const trimmed = text.trim();
    if (trimmed.length < 3 || pending) return;

    setMessages((current) => [...current, { id: nextId(), role: 'user', text: trimmed }]);
    setQuestion('');
    setPending(true);

    try {
      const result = await api.ask({
        question: trimmed,
        ward_id: selectedWardId || null,
        language,
      });
      setMessages((current) => [
        ...current,
        {
          id: nextId(),
          role: 'agent',
          text: result.answer,
          trace: result.trace,
          engine: result.engine,
          llm: result.llm,
          elapsedMs: result.elapsed_ms,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: nextId(),
          role: 'agent',
          failed: true,
          text: error?.message || 'The orchestrator could not answer that.',
        },
      ]);
    } finally {
      setPending(false);
    }
  }

  const engine = catalogue?.engine;
  const toolCount = catalogue?.tools?.length ?? 0;

  return (
    <section className="card flex flex-col p-5">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-bold leading-tight">
            Ask Aeris
            <span className="ml-2 align-middle text-xs font-medium text-muted">
              multi-agent orchestrator
            </span>
          </h2>
          <p className="mt-1 text-xs text-muted">
            One question, routed across the forecasting, attribution, and enforcement agents.
          </p>
        </div>
        {engine ? (
          <span className="chip" title={`${toolCount} agent tools registered`}>
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: engine === 'langgraph' ? '#A3C853' : '#8291AA' }}
              aria-hidden="true"
            />
            {engine === 'langgraph' ? 'LangGraph' : 'Deterministic'} · {toolCount} tools
          </span>
        ) : null}
      </header>

      <ul
        ref={listRef}
        className="mb-3 flex max-h-96 min-h-[11rem] flex-col gap-4 overflow-y-auto pr-1"
        aria-live="polite"
        aria-busy={pending}
      >
        {messages.length === 0 && !pending ? (
          <li className="rounded-xl border border-dashed border-edge p-4 text-sm leading-relaxed text-muted">
            Ask about a ward's outlook, what is driving its pollution, or where to send inspection
            teams. Every answer shows which agents were called.
          </li>
        ) : (
          messages.map((message) => <Message key={message.id} message={message} />)
        )}
        {pending ? (
          <li className="flex items-center gap-2 text-sm text-muted">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-edge border-t-accent" />
            Consulting agents…
          </li>
        ) : null}
      </ul>

      {messages.length === 0 ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => ask(suggestion)}
              disabled={pending}
              className="rounded-lg border border-edge bg-raised px-2.5 py-1.5 text-xs text-muted transition-colors hover:bg-line hover:text-ink disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
        className="flex gap-2"
      >
        <label className="sr-only" htmlFor="orchestrator-question">
          Ask the orchestrator a question
        </label>
        <input
          id="orchestrator-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={
            selectedWardName ? `Ask about ${selectedWardName} or the whole city…` : 'Ask a question…'
          }
          maxLength={1000}
          className="min-w-0 flex-1 rounded-xl border border-edge bg-raised px-3 py-2.5 text-sm text-ink placeholder:text-muted/70"
        />
        <button
          type="submit"
          disabled={pending || question.trim().length < 3}
          className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-canvas transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Ask
        </button>
      </form>

      {engine === 'deterministic' ? (
        <p className="mt-2.5 text-[11px] leading-relaxed text-muted">
          No LLM key configured, so questions are routed to the agents by keyword. Set an API key in
          the backend <code className="text-ink">.env</code> to enable LangGraph planning.
        </p>
      ) : null}
    </section>
  );
}
