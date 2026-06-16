import { useEffect } from "react";

// Force a `data-theme` on <html> for the lifetime of a page, restoring whatever
// was there before on unmount (not just clearing it).
export function useForcedTheme(theme: "light" | "dark") {
  useEffect(() => {
    const root = document.documentElement;
    const prev = root.getAttribute("data-theme");
    root.setAttribute("data-theme", theme);
    return () => {
      if (prev) root.setAttribute("data-theme", prev);
      else root.removeAttribute("data-theme");
    };
  }, [theme]);
}
