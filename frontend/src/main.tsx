import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { initErrorReporting } from "./lib/sentry";
import { applyTheme } from "./lib/theme";
import "./index.css";

void initErrorReporting(); // no-op unless VITE_SENTRY_DSN was set at build time
applyTheme(); // before first paint, so dark-mode users never see a white flash

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
