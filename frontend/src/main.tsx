import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Link, RouterProvider } from "react-router-dom";
import Layout from "./components/Layout";
import "./index.css";
import Clusters from "./pages/Clusters";
import EntityDetail from "./pages/EntityDetail";
import FindingDetail from "./pages/FindingDetail";
import Findings from "./pages/Findings";
import Overview from "./pages/Overview";
import Reports from "./pages/Reports";
import Results from "./pages/Results";
import ReviewQueue from "./pages/ReviewQueue";
import Trends from "./pages/Trends";
import Upload from "./pages/Upload";

function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-lg font-semibold">Page not found</h1>
      <Link to="/" className="mt-2 inline-block text-accent hover:underline">Back to overview</Link>
    </div>
  );
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "entities/:id", element: <EntityDetail /> },
      { path: "findings", element: <Findings /> },
      { path: "findings/:id", element: <FindingDetail /> },
      { path: "clusters", element: <Clusters /> },
      { path: "trends", element: <Trends /> },
      { path: "review", element: <ReviewQueue /> },
      { path: "upload", element: <Upload /> },
      { path: "results", element: <Results /> },
      { path: "reports", element: <Reports /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
