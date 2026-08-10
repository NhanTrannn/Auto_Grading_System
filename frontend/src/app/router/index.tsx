import { Navigate, createBrowserRouter } from "react-router-dom";

import DashboardLayout from "@/app/layouts/DashboardLayout";
import DashboardPage from "@/pages/DashboardPage";
import JobDetailPage from "@/pages/JobDetailPage";
import OcrPage from "@/pages/OcrPage";

export const router = createBrowserRouter([
  {
    element: <DashboardLayout />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/jobs/:jobId", element: <JobDetailPage /> },
      { path: "/ocr", element: <Navigate to="/ocr/roi" replace /> },
      { path: "/ocr/:moduleId", element: <OcrPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
