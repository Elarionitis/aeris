import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Load a resource, aborting the in-flight request when inputs change.
 *
 * Returns { data, error, loading, reload }. An aborted request never surfaces
 * as an error, so switching wards quickly does not flash a failure state.
 */
export function useResource(loader, deps, { enabled = true, keepPrevious = false } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(Boolean(enabled));
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError('');
    if (!keepPrevious) setData(null);

    loaderRef
      .current(controller.signal)
      .then((payload) => {
        if (active) setData(payload);
      })
      .catch((caught) => {
        if (!active || caught?.name === 'AbortError') return;
        setError(caught?.message || 'Failed to load data');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { data, error, loading, reload };
}
