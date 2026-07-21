import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, apiRequest } from "../api/client";

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const login = useMutation({
    mutationFn: () =>
      apiRequest<void>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["current-user"] });
      navigate("/", { replace: true });
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (username && password) login.mutate();
  }

  const errorMessage =
    login.error instanceof ApiError
      ? login.error.message
      : login.error
        ? "登录失败，请稍后重试"
        : null;

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand-mark" aria-hidden="true">
          财
        </div>
        <p className="eyebrow">FINANCE TOOLKIT</p>
        <h1 id="login-title">登录财务工具包</h1>
        <p className="muted">使用部署时配置的管理员账号继续。</p>
        <form onSubmit={handleSubmit} className="form-stack">
          <label>
            用户名
            <input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label>
            密码
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {errorMessage ? (
            <div role="alert" className="inline-error">
              {errorMessage}
            </div>
          ) : null}
          <button
            className="button button-primary"
            type="submit"
            disabled={login.isPending}
          >
            {login.isPending ? "正在登录…" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
