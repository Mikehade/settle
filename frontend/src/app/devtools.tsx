import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools";

/** Development-only panels. Loaded lazily from the root route, so production never ships them. */
export default function Devtools() {
  return (
    <>
      {/* Both on the right, so neither covers the user menu at the bottom of the sidebar. */}
      <TanStackRouterDevtools
        position="bottom-right"
        toggleButtonProps={{ style: { transform: "translateX(-3.5rem)" } }}
      />
      <ReactQueryDevtools buttonPosition="bottom-right" />
    </>
  );
}
