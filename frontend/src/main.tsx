import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { setWorkerUrl } from "maplibre-gl";
import App from "./App";
import "@fontsource-variable/inter";
import "@fontsource-variable/newsreader";
import "./tokens.css";

// See scripts/copy-maplibre-worker.mjs for why this is needed.
setWorkerUrl("/maplibre-gl-worker.mjs");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
