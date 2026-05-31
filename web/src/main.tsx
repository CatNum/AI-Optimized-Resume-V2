import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { ChatPage } from "./pages/ChatPage";
import { OutputsPage } from "./pages/OutputsPage";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/outputs" element={<OutputsPage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
