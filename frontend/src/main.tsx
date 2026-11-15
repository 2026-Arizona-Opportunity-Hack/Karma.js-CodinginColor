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
import { DashboardPage } from "./pages/DashboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import { InvitePage } from "./pages/InvitePage";
import { ApiKeysPage } from "./pages/ApiKeysPage";

const queryClient = new QueryClient();

const SCREENS = [
  { path: "/messages", title: "Messages", phase: "Phase 4" },
  { path: "/reports", title: "Reports", phase: "Phase 4" },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/invite/:token" element={<InvitePage />} />
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="/donors" element={<DonorsPage />} />
            <Route path="/donors/:donorId" element={<DonorDetailPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/settings/api-keys" element={<ApiKeysPage />} />
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
