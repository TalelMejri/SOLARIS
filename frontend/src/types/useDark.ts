import { useSyncExternalStore } from "react";

const subscribe = (cb: () => void) => {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => mo.disconnect();
};
const getSnapshot = () => document.documentElement.classList.contains("dark");

/** true when the shadcn / next-themes `.dark` class is on <html> */
export function useIsDark() {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}