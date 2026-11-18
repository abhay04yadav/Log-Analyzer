import { useCallback, useEffect, useRef, useState } from "react";

// Calls `fn` now and every `ms` milliseconds; returns { data, error, reload }.
export function usePoll(fn, ms, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
    if (!ms) return undefined;
    const id = setInterval(reload, ms);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, reload, ...deps]);

  return { data, error, reload };
}
