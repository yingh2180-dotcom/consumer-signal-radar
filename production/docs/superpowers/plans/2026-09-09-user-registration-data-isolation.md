# User Registration and Data Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add username/password registration with automatic login, retain administrator login, share built-in sample projects, and isolate every user's private project data.

**Architecture:** Add persistent users and identity-bearing sessions to SQLite, then centralize project visibility and write authorization in backend helpers. Existing projects become read-only system samples; a user copies a sample into a private project before changing or analyzing it. The React client uses explicit login, registration, and administrator modes and renders controls from the server-provided role and ownership fields.

**Tech Stack:** FastAPI, Pydantic, SQLite, Python `hashlib.scrypt`, React, Vite, unittest.

## Global Constraints

- Registration uses username and password without email, SMS, or third-party authentication.
- Username is 3–32 Chinese characters, letters, digits, underscores, or hyphens; ASCII case is ignored for uniqueness.
- Password is 8–128 characters and is stored only as a salted scrypt hash.
- System samples are visible to all authenticated accounts and remain read-only.
- User projects and all descendants are visible only to their owner.
- Existing projects migrate to system samples without record loss.
- Only the administrator may read detailed model settings or call `POST /api/settings`.
- Unauthorized object access returns 404; unauthenticated access returns 401.
- No password or API Key may appear in API responses, logs, frontend bundles, or snapshots.

---

### Task 1: Database migration and identity primitives

**Files:**
- Modify: `backend/db.py`
- Modify: `backend/server.py`
- Test: `backend/test_server.py`

**Interfaces:**
- Produces: `users(id, username_norm, display_name, password_hash, role, status, created_at)`; identity-bearing `sessions`; project fields `owner_type`, `owner_user_id`, and `source_project_id`.
- Produces: `hash_password(password) -> str`, `verify_password(password, encoded) -> bool`, and `normalize_username(username) -> tuple[str, str]`.

- [ ] Write migration tests that open a legacy database, record entity counts, initialize the new schema twice, and assert unchanged counts plus `owner_type='system'` for legacy projects.
- [ ] Run `..\.venv\Scripts\python.exe -m unittest backend.test_server.ApiTests.test_identity_schema_migrates_legacy_data -v` and confirm it fails before implementation.
- [ ] Implement an idempotent transaction that creates `users`, rebuilds or extends `sessions`, adds project ownership columns, marks legacy projects as system samples, and clears legacy anonymous sessions.
- [ ] Add scrypt helpers using a fresh 16-byte salt and `hmac.compare_digest`; validate username normalization without storing plaintext passwords.
- [ ] Run the migration and hashing tests and confirm they pass.

### Task 2: Registration, user login, administrator login, and roles

**Files:**
- Modify: `backend/server.py`
- Test: `backend/test_server.py`

**Interfaces:**
- Produces: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/admin-login`, and identity response `{id, username, role}` from `GET /api/auth/me`.
- Consumes: user/session tables and password helpers from Task 1.

- [ ] Add tests for successful registration with automatic session, duplicate normalized username, invalid username/password, user re-login, administrator login, logout, generic failed-login response, and absence of password hashes in responses.
- [ ] Run the focused authentication tests and confirm they fail before route implementation.
- [ ] Add request models with exact length constraints and server-side username validation.
- [ ] Create registration and login transactions; rotate opaque session tokens after successful authentication and attach role/user identity to the session.
- [ ] Update authentication middleware to place immutable identity on `request.state.identity`.
- [ ] Keep the existing administrator password hash and expose it only through `/api/auth/admin-login`.
- [ ] Run focused authentication tests and confirm they pass.

### Task 3: Centralized project authorization and public sample copying

**Files:**
- Modify: `backend/server.py`
- Modify: `backend/db.py` only if a query helper belongs there
- Test: `backend/test_server.py`

**Interfaces:**
- Produces: `visible_project_or_404(project_id, identity, write=False)` and `POST /api/projects/{project_id}/copy`.
- Produces project response fields `owner_type`, `is_owner`, and `source_project_id`.

- [ ] Add two-user tests covering project list visibility, direct cross-user reads, uploads, review changes, analysis jobs, cancellation/retry, insights, evaluation, reports, exports, and backups; expect 404 for cross-user object IDs.
- [ ] Add tests proving both users see system samples, cannot mutate them, and receive private independent copies from the copy endpoint.
- [ ] Run the authorization tests and confirm the existing unfiltered routes fail them.
- [ ] Implement the centralized project resolver and apply it to every route that accepts project, comment, job, report, or evaluation identifiers.
- [ ] Filter project lists to `owner_type='system' OR owner_user_id=current_user.id`; assign new projects to the current user.
- [ ] Implement transactional sample copying with provenance through `source_project_id`; copy comments and required metadata, then return the new private project.
- [ ] Run the two-user authorization suite and confirm it passes.

### Task 4: Restrict model configuration by role

**Files:**
- Modify: `backend/server.py`
- Test: `backend/test_server.py`

**Interfaces:**
- Administrator `GET /api/settings` returns existing non-secret detail.
- User `GET /api/settings` returns only `{configured, paid_enabled, max_rows}`.
- `POST /api/settings` returns 403 for non-administrators.

- [ ] Write role tests for detailed administrator settings, redacted user settings, denied user updates, and unchanged API Key non-disclosure.
- [ ] Run the focused settings tests and confirm user requests expose too much or are not forbidden before the change.
- [ ] Add role guards to settings endpoints and keep API Key write-only.
- [ ] Run all settings tests and confirm they pass.

### Task 5: Login, registration, account display, and ownership UI

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/ModelConfigPanel.jsx`
- Modify: `frontend/src/styles.css`
- Test/build: `frontend/package.json` scripts and production build

**Interfaces:**
- Consumes authentication and project ownership responses from Tasks 2–4.
- Produces login modes `user-login`, `register`, `admin-login`; sends `{username,password}` for users and `{password}` for administrators.

- [ ] Build a login/register mode switch with username, password, confirmation, inline constraints, busy state, and accessible labels.
- [ ] On successful registration, use the returned session and load the workspace immediately.
- [ ] Display current username and role near the exit action.
- [ ] Mark public projects as “系统样本”, hide mutation controls, and add “复制到我的项目”.
- [ ] Hide the model configuration launcher and write form for regular users; render only model availability where needed.
- [ ] Clear password fields on mode change, success, logout, and component unmount.
- [ ] Run `npm.cmd run build`; expect a successful Vite production build.

### Task 6: Full regression, browser isolation scenario, and documentation

**Files:**
- Modify: `docs/03_操作说明书.md`
- Modify: `docs/02_技术架构说明.md`
- Modify: `docs/06_测试与验收说明.md`
- Modify: `docs/08_开发者维护手册.md`

**Interfaces:**
- Consumes all prior from Tasks 1–5.

- [ ] Run `..\.venv\Scripts\python.exe -m unittest backend.test_engine backend.test_server backend.test_runtime -v`; expect all tests to pass without outbound model calls.
- [ ] Back up the current runtime database, start the upgraded service, and verify migration counts before and after are equal.
- [ ] In a browser, register users A and B; verify both see system samples, A creates/imports/analyzes private data, B cannot see or request it, and A still sees it after logout and service restart.
- [ ] Verify administrator login can edit model configuration and a regular user cannot see or call that interface.
- [ ] Run a production frontend build and confirm the served page references the new hashed assets.
- [ ] Update user, architecture, testing, and maintenance documentation with the final routes, ownership rules, recovery steps, and verified results.
- [ ] Search source, responses, logs, bundle text, and documents for test passwords/API Keys; remove any secret material and retain only placeholders.
