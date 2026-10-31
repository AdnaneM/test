import { useCallback, useEffect, useRef, useState, type DependencyList, type Dispatch, type SetStateAction } from "react";

export interface AsyncState<T> {
  data: T | null;
  /** Erreur brute (à formater avec humanError) ou null. */
  error: unknown;
  loading: boolean;
  reload: () => void;
  setData: Dispatch<SetStateAction<T | null>>;
}

/**
 * Exécute une promesse à chaque changement de `deps` ; ignore les réponses
 * obsolètes et conserve les données précédentes pendant le rechargement.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: DependencyList): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fnRef.current().then(
      (d) => {
        if (cancelled) return;
        setData(d);
        setLoading(false);
      },
      (e: unknown) => {
        if (cancelled) return;
        setData(null);
        setError(e ?? new Error("Erreur inconnue"));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}
