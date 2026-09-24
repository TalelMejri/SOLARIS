import { useAuth } from "@/contexts/AuthContext";
import { Navigate, Outlet } from "react-router-dom";

export default function PublicRoute() {
  const { isAuth } = useAuth();

  if (isAuth) return <Navigate to="/dashboard" replace />;

  return <Outlet />;
}