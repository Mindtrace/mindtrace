# Poseidon Web Application

Poseidon is a modular, role-based web application built with [Reflex](https://reflex.dev/), featuring dashboards, management, authentication, and user profile pages. The backend uses MongoDB for data storage.

## Features

- **Role-based navigation:** User, Admin, and Super Admin dashboards and management.
- **Modular components:** Unified, reusable UI components for forms, tables, popups, cards, headers, layouts, stats, inputs, and buttons.
- **Authentication:** Login and registration with optional admin registration key.
- **Organization and user management:** Admins and super admins can manage users and organizations.
- **Profile management:** Users can view and edit their profiles.
- **MongoDB backend:** All data is persisted in MongoDB.

---

## Directory Structure

```
poseidon/
├── backend/           # Backend logic, services, database models, repositories
│   └── database/
│       ├── models/        # Data models: user, organization, project
│       └── repositories/  # Repository pattern for data access
├── components/        # Reusable UI components
│   ├── sidebar.py
│   ├── forms.py
│   ├── tables.py
│   ├── popups.py
│   ├── headers.py
│   ├── cards.py
│   ├── layouts.py
│   ├── stats.py
│   ├── inputs.py
│   ├── buttons.py
│   └── utilities.py
├── pages/             # Application pages
│   ├── index.py           # Landing page
│   ├── user/
│   │   └── profile.py     # User profile page
│   ├── management/
│   │   ├── organization_management.py
│   │   └── user_management.py
│   ├── dashboards/
│   │   ├── admin.py
│   │   └── super_admin.py
│   └── auth/
│       ├── register.py
│       └── login.py
├── state/             # State management for auth, user, org
├── assets/            # Static assets (e.g., mindtrace-logo.png)
├── styles/            # Custom styles
├── utils/             # Utility functions
└── rxconfig.py        # Reflex app configuration
```

---

## Components

- **Sidebar:** Role-based navigation menu with logo and sectioned links.
- **Forms:** Unified form components for login, registration, and management.
- **Tables:** Reusable tables for user and organization management.
- **Popups:** Modal dialogs for editing, viewing, and confirming actions.
- **Headers:** Unified app and section headers.
- **Cards:** Dashboard and summary cards.
- **Layouts:** Page and section layout containers.
- **Stats:** Statistic display components.
- **Inputs & Buttons:** Standardized input fields and button styles.

---

## Pages

- **Landing Page:** `/` — Welcome and app overview.
- **Profile:** `/profile` — User profile view/edit.
- **User Management:** `/user-management` — Admin/super admin user management.
- **Organization Management:** `/organization-management` — Admin/super admin org management.
- **Dashboards:**
  - `/admin` — Admin dashboard.
  - `/super-admin` — Super admin dashboard.
- **Authentication:**
  - `/login` — User login.
  - `/register` — User/admin registration (with optional admin key).

---

## Backend

- **Database:** MongoDB (run via Docker)
- **Models:** User, Organization, Project (see `backend/database/models/`)
- **Repositories:** Data access layer for each model (see `backend/database/repositories/`)
- **State Management:** Auth, user, and organization state in `state/`

---

## Static Assets

- **Logo:** `assets/mindtrace-logo.png` (used in sidebar and headers)

---

## Setup & Running

### 1. Start MongoDB

```bash
docker run -d --name mongodb -p 27017:27017 mongo:latest
```

### 2. Sync Python environment

From the project root:

```bash
uv sync
```

### 3. Start the Reflex app

```bash
cd mindtrace/ui/mindtrace/ui/poseidon
uv run reflex run
```

---

## Formatting & Linting

```bash
uv run ruff format
uv run ruff check --fix
```

## Configuration

- The Reflex app is configured in `rxconfig.py`.
- By default, the app uses SQLite for development (`db_url="sqlite:///poseidon.db"`), but the backend logic is designed for MongoDB. Ensure your backend services connect to MongoDB as needed.

---

## Notes

- All UI logic is defined at the page level; components are purely presentational.
- Components and headers are unified and reused across all pages.
- Admin registration requires an organization-specific key, which can be viewed by super admins in the organization management table. 