const configuredApiUrl = import.meta.env.VITE_API_URL?.trim().replace(/\/+$/, "");

export const env = {
  /** Origin the API is served from. Unset means the app's own origin (the dev proxy). */
  apiUrl: configuredApiUrl || window.location.origin,
} as const;
