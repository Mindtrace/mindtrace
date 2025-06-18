# Reflex App Design & Progress

## 1. Overview
This document tracks the design plan, progress, and key decisions for the Reflex-based application.

---

## 2. App Structure & Flow

### Authentication
- **Register Page**: New users sign up (username, email, password).
- **Login Page**: Existing users log in (email, password).
- **Auth Implementation**: Custom authentication system with:
  - `AuthState` class managing login/register state and error handling
  - `AuthService` backend service for user authentication and registration
  - Custom exception handling (UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError)
  - Token-based authentication flow
- **After login**: Redirect to main Data Viewer page.
- **Page protection**: All other pages require authentication (to be implemented with auth guards).

### Main Feature: Data Viewer
- **Displays**: Grid/list of images (or other data) from backend (MongoDB, GCP, etc.).
- **UI**: Thumbnails, titles, summaries; click for modal with details.
- **Pagination**: For large datasets.
- **Backend**: Fetch data from MongoDB via Mindtrace ODM; images via presigned GCP URLs (to be implemented).

### Layout & Navigation
- **Top Navbar**: Implemented with navigation links and active state highlighting.
- **Current Navigation**: Home, Login, Register (Logout to be added after auth guards).
- **Consistent Theming**: Using Reflex theme system with bronze accent color and custom styling.

### User Management (Optional for v1)
- **Admin-only page**: List/add/delete users, assign roles.

### Routing Table
| Route         | Page                | Access           |
|---------------|---------------------|------------------|
| `/register`   | Register            | Public           |
| `/login`      | Login               | Public           |
| `/`           | Data Viewer         | Authenticated    |
| `/users`      | User Management     | Admin only (opt) |

---

## 3. Progress Checklist
- [x] Set up authentication pages with custom auth system
- [x] Implement basic layout (navbar) and routing structure
- [x] Implement comprehensive styling system with design tokens, utilities, and responsive patterns
- [ ] Add authentication guards for page protection
- [ ] Build Data Viewer page (fetch data, display grid, modal, pagination)
- [x] Connect to MongoDB backend via Mindtrace ODM
- [ ] Implement GCP presigned URLs for images
- [ ] (Optional) Add user management for admins
- [x] Document design system and conventions

---

## 4. Design Decisions & Notes
- **Custom Authentication**: Implemented custom auth system instead of reflex-local-auth for more control
- **Token-based Auth**: Using JWT tokens for session management (stored in AuthState)
- **Error Handling**: Comprehensive exception handling for auth flows
- **Backend Architecture**: Structured with services layer and custom exceptions
- **Comprehensive Styling System**: Implemented scalable styling architecture with:
  - Design tokens (colors, spacing, typography, breakpoints)
  - Utility functions for common patterns (cards, buttons, inputs, layouts)
  - Global and component-specific styles
  - Dark mode support with CSS variables
  - Responsive design patterns and breakpoints
  - Custom CSS classes and animations
- Use event handlers for all private data access (never expose sensitive data in static page code)
- Extend user model/state for roles, company, etc. as needed
- Use Reflex theming for consistent look and feel (bronze accent theme implemented)
- ✅ Custom design system implemented with comprehensive utility functions

---

## 5. Contributors
- Please update this file with progress, design changes, or questions! 