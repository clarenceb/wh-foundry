# Copilot Instructions for wh-foundry

## Python Environment

- Always use **uv** for all Python and virtual environment operations.
- Use `uv venv .venv` to create virtual environments.
- Use `uv pip install <package>` to install packages (instead of `pip install`).
- Use `uv pip uninstall <package>` to remove packages.
- Use `uv pip list` to list installed packages.
- Use `uv pip freeze` to generate requirements.
- Activate the venv with `source .venv/bin/activate` before running Python scripts.

## Frontend Preferences

- Use **React** with **TypeScript** for all frontend code.
- Use **Vite** as the build tool and dev server.
- Use **Zustand** for state management (not Redux or Context).
- Prefer functional components with hooks.
- Use CSS modules or inline styles — no CSS-in-JS libraries.
- Frontend project lives in the `web/` directory.
