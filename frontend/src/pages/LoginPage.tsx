import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";

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
      <div className="login-card-stack">
        <div className="login-blue-layer" aria-hidden="true" />
        <section className="login-card" aria-labelledby="login-title">
          <div className="login-identity">
            <img
              className="brand-mark login-brand-mark"
              src="/prefine-logo-512.png"
              alt=""
            />
            <p className="login-brand-name">PreFine</p>
          </div>
          <h1 id="login-title" className="login-title">
            登录
          </h1>
          <form onSubmit={handleSubmit} className="login-form">
            <label className="login-field">
              管理员账号
              <input
                name="username"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label className="login-field">
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
              className="button login-submit"
              type="submit"
              disabled={login.isPending}
            >
              {login.isPending ? "正在登录…" : "登录"}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
