import { useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { subscribeUnauthorized } from "../api/session";

export function SessionBoundary({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  useEffect(
    () =>
      subscribeUnauthorized(() => {
        queryClient.removeQueries();
        navigate("/login", { replace: true });
      }),
    [navigate, queryClient],
  );

  return children;
}
