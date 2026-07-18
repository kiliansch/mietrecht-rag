import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { SessionProvider } from "./state/session";
import { WorkspaceProvider } from "./state/workspace";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SessionProvider>
      <WorkspaceProvider>
        <App />
      </WorkspaceProvider>
    </SessionProvider>
  </StrictMode>,
);
