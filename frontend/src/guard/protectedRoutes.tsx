import { useAuth } from "@/contexts/AuthContext";
import { Navigate, Outlet } from "react-router-dom";


export default function ProtectedRoute() {
    const { isAuth } = useAuth();
    if (!isAuth) return <Navigate to="/login" replace />;
    return <Outlet />;
}