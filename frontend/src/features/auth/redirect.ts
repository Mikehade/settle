export const DEFAULT_SIGNED_IN_PATH = "/cases";

/** Only same-app paths are followed after sign-in, never another origin (`//evil.example`). */
export function safeRedirect(target: string | undefined) {
  if (!target?.startsWith("/") || target.startsWith("//")) return DEFAULT_SIGNED_IN_PATH;
  return target;
}
