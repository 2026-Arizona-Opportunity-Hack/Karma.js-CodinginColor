import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import "./index.css";
import { LoginPage } from "./pages/LoginPage";
import { ImportPage } from "./pages/ImportPage";
import { ReviewPage } from "./pages/ReviewPage";
import { DonorsPage } from "./pages/DonorsPage";
import { DonorDetailPage } from "./pages/DonorDetailPage";
import { DashboardPage } from "./pages/DashboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import { InvitePage } from "./pages/InvitePage";
import { ApiKeysPage } from "./pages/ApiKeysPage";
import { FieldsPage } from "./pages/FieldsPage";
import { MessagesPage } from "./pages/MessagesPage";
import { ReportsPage } from "./pages/ReportsPage";

const queryClient = new QueryClient();

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
            <Route path="/messages" element={<MessagesPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/settings/api-keys" element={<ApiKeysPage />} />
            <Route path="/settings/fields" element={<FieldsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
