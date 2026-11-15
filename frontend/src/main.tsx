import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import "./index.css";
import { LoginPage } from "./pages/LoginPage";
import { ImportPage } from "./pages/ImportPage";
import { ReviewPage } from "./pages/ReviewPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { DonorsPage } from "./pages/DonorsPage";
import { DonorDetailPage } from "./pages/DonorDetailPage";

const queryClient = new QueryClient();

const SCREENS = [
  { path: "/", title: "Dashboard", phase: "Phase 3" },
  { path: "/messages", title: "Messages", phase: "Phase 4" },
  { path: "/reports", title: "Reports", phase: "Phase 4" },
  { path: "/settings", title: "Settings", phase: "Phase 3" },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<Layout />}>
            <Route path="/donors" element={<DonorsPage />} />
            <Route path="/donors/:donorId" element={<DonorDetailPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/review" element={<ReviewPage />} />
            {SCREENS.map((s) => (
              <Route
                key={s.path}
                path={s.path}
                element={<PlaceholderPage title={s.title} phase={s.phase} />}
              />
            ))}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
