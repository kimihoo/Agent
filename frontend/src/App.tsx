import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import Chat from "./pages/Chat";
import Login from "./pages/Login";
import Knowledge from "./pages/Knowledge";
import Contracts from "./pages/Contracts";
import ContractDetail from "./pages/ContractDetail";
import Admin from "./pages/Admin";

function Guard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="loading-screen">加载中…</div>;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <Guard>
            <Layout />
          </Guard>
        }
      >
        <Route path="/" element={<Chat />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/contracts" element={<Contracts />} />
        <Route path="/contracts/:id" element={<ContractDetail />} />
        <Route path="/admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
