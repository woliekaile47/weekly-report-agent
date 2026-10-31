// DeerFlow e0f5483, MIT.
import * as React from "react";

const MOBILE_BREAKPOINT = 768;
function getServerSnapshot() {
  return false;
}

export function useIsMobile(breakpoint = MOBILE_BREAKPOINT) {
  const query = `(max-width: ${breakpoint - 1}px)`;
  const subscribe = React.useCallback(
    (callback: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", callback);
      return () => mql.removeEventListener("change", callback);
    },
    [query],
  );
  const getSnapshot = React.useCallback(
    () => window.matchMedia(query).matches,
    [query],
  );
  return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
