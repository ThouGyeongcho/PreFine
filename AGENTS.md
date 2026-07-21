# Repository Guidelines

## Project Structure & Module Organization

This repository is specification-first. Accepted decisions live in `docs/superpowers/specs/2026-07-21-finance-toolkit-design.md`; read it before changing behavior.

Keep the implementation split by responsibility:

- `backend/app/`: FastAPI routes and the `money`, `tax_source`, `calendar`, `tax_profile`, `reminders`, and `auth` modules.
- `backend/tests/`: pytest unit and API tests mirroring backend modules.
- `backend/migrations/`: Alembic migrations for SQLite.
- `frontend/src/`: React/TypeScript pages, reusable components, API clients, and tool-local settings.
- `frontend/e2e/`: Playwright user-flow tests.
- `docs/`: design and operational documentation.

Do not commit `.superpowers/`, local databases, build output, or secrets.

## Build, Test, and Development Commands

Project manifests are not yet present. When scaffolding lands, standardize on these commands:

- `docker compose up --build`: build and run the complete single-container application.
- `python -m pytest backend/tests`: run backend unit and API tests.
- `npm --prefix frontend run dev`: start Vite locally.
- `npm --prefix frontend run lint`: run TypeScript linting and formatting checks.
- `npm --prefix frontend run test`: run Vitest component tests.
- `npm --prefix frontend run build`: create the production frontend bundle.
- `npm --prefix frontend run e2e`: run Playwright acceptance tests.

## Coding Style & Naming Conventions

Use Python 3.12, four-space indentation, type hints, Ruff formatting/linting, and `snake_case` modules and functions. Use `Decimal` for all money calculations; never use binary floats.

Use TypeScript with two-space indentation, ESLint/Prettier, `PascalCase` React components, `camelCase` functions, and `useXxx` hook names. Keep API JSON fields in `snake_case`. Place business settings beneath their owning tool rather than in global settings.

## Testing Guidelines

Use pytest for backend logic, Vitest with React Testing Library for components, and Playwright for critical flows. Name Python tests `test_<behavior>.py` and frontend tests `*.test.ts(x)`. Every bug fix requires a regression test. Tax-calendar tests must prove that official `bssz` text remains unchanged and unknown items appear as “其他待确认.”

## Commit & Pull Request Guidelines

There is no established Git history yet. Use Conventional Commits, for example `feat(tax): add taxpayer profile filtering` or `fix(money): reject three-decimal input`.

Pull requests should include a summary, linked issue, test results, migration/configuration notes, and UI screenshots. Call out 12366 mapping changes explicitly.

## Security & Configuration

Never commit `.env` files, credentials, SMTP secrets, session keys, or `/data/*.db`. Keep secrets in Docker environment variables and document new variables in `.env.example`. Preserve the single-worker constraint unless reminder scheduling is moved to shared infrastructure.
