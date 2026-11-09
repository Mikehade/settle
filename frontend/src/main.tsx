import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/app";
import { syncSessionAcrossTabs } from "@/lib/session";
import { watchSystemTheme } from "@/lib/theme";

import "@/styles/globals.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element in index.html");

syncSessionAcrossTabs();
watchSystemTheme();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
