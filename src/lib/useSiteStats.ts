import { useEffect, useState } from "react";

const PROD_DATA = import.meta.env.VITE_PROD_DATA === "true";
const STATIC_ORIGIN = PROD_DATA ? "https://askanastronaut.issinrealtime.org" : "";

const SITE_STATS_URL = `${STATIC_ORIGIN}/static_assets/data/site_stats.json`;

export function useSiteStats(): SiteStats | null {
  const [data, setData] = useState<SiteStats | null>(null);

  useEffect(() => {
    fetch(SITE_STATS_URL)
      .then((r) => r.json() as Promise<SiteStats>)
      .then(setData)
      .catch((err) => console.error("Failed to load site_stats.json:", err));
  }, []);

  return data;
}
