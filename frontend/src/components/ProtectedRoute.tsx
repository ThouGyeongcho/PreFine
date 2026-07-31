import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router";

import { ApiError, apiRequest } from "../api/client";
import type { CurrentUser } from "../api/types";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const currentUser = useQuery({
    queryKey: ["current-user"],
    queryFn: () => apiRequest<CurrentUser>("/api/auth/me"),
    retry: false,
  });

  if (currentUser.isPending) {
    return (
      <div className="route-loading" role="status">
        正在载入…
      </div>
    );
  }
  if (
    currentUser.error instanceof ApiError &&
    currentUser.error.status === 401
  ) {
    return <Navigate to="/login" replace />;
  }
  if (currentUser.isError) {
    return (
      <div className="route-error" role="alert">
        无法连接服务，请稍后刷新。
      </div>
    );
  }
  return children;
}
