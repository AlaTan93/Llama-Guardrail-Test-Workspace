import { Navigate, Route, Routes, useNavigate } from "react-router";
import { Header } from "./components/Header";
import RunDetailPage from "./pages/RunDetailPage";
import RunsPage from "./pages/RunsPage";

export default function App() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <Header />
      <main className="mx-auto max-w-6xl p-5">
        <Routes>
          <Route path="/" element={<RunsPage onOpen={(id) => navigate(`/runs/${id}`)} />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
