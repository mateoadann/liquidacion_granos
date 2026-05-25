import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export function usePageQueryParam(defaultPage = 1): [number, (next: number) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("page");
  const parsed = raw ? Number.parseInt(raw, 10) : defaultPage;
  const page = Number.isFinite(parsed) && parsed >= 1 ? parsed : defaultPage;

  const setPage = useCallback(
    (next: number) => {
      setSearchParams(
        (prev) => {
          const updated = new URLSearchParams(prev);
          if (next <= 1) {
            updated.delete("page");
          } else {
            updated.set("page", String(next));
          }
          return updated;
        },
        { replace: false },
      );
    },
    [setSearchParams],
  );

  return [page, setPage];
}
