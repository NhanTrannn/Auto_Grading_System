import { Navigate, createBrowserRouter } from "react-router-dom";

import DashboardLayout from "@/app/layouts/DashboardLayout";
import BaremBuilderPage from "@/pages/BaremBuilderPage";
import DashboardPage from "@/pages/DashboardPage";
import JobDetailPage from "@/pages/JobDetailPage";
import OcrPage from "@/pages/OcrPage";
import PipelineJobPage from "@/pages/PipelineJobPage";
import PipelinePage from "@/pages/PipelinePage";

export const router = createBrowserRouter([
  {
    element: <DashboardLayout />,
    children: [
      { path: "/", element: <DashboardPage /> },
      { path: "/jobs/:jobId", element: <JobDetailPage /> },
      { path: "/pipeline", element: <PipelinePage /> },
      { path: "/pipeline/:jobId", element: <PipelineJobPage /> },
      { path: "/barem", element: <BaremBuilderPage /> },
      { path: "/ocr", element: <Navigate to="/ocr/roi" replace /> },
      { path: "/ocr/:moduleId", element: <OcrPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
