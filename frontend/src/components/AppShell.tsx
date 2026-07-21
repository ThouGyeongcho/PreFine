import { type ReactNode, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { apiRequest } from "../api/client";

const navigation = [
  { to: "/", label: "工作台", icon: "⌂", end: true },
  { to: "/money", label: "金额大小写转换", icon: "¥", end: false },
  { to: "/calendar", label: "税收日历", icon: "日", end: false },
  { to: "/system", label: "系统设置", icon: "⚙", end: false },
];

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();

  async function logout() {
    await apiRequest<void>("/api/auth/logout", { method: "POST" });
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-frame">
      <header className="mobile-header">
        <button
          className="icon-button"
          type="button"
          aria-label="打开导航"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((value) => !value)}
        >
          ☰
        </button>
        <span>PreFine</span>
      </header>
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <span className="brand-mark brand-mark-small" aria-hidden="true">
            财
          </span>
          <span>PreFine</span>
        </div>
        <nav aria-label="主导航" className="primary-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                isActive ? "nav-link nav-link-active" : "nav-link"
              }
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button
          className="sidebar-logout"
          type="button"
          onClick={() => void logout()}
        >
          退出登录
        </button>
      </aside>
      {menuOpen ? (
        <button
          className="drawer-backdrop"
          aria-label="关闭导航"
          onClick={() => setMenuOpen(false)}
        />
      ) : null}
      <main className="workspace">{children}</main>
    </div>
  );
}
