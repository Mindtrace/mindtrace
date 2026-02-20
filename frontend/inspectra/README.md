# Inspectra Frontend

Auth UI for Inspectra: login, app shell (sidebar), and role-based management of organizations and users. Built with Next.js, TypeScript, Tailwind CSS, TanStack Query, and shadcn UI.

## Tech Stack

- **Framework**: Next.js 16 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **State Management**: TanStack Query (React Query)
- **Validation**: Zod
- **UI Components**: shadcn/ui
- **API Types**: openapi-typescript (for FastAPI backend integration)
- **Testing**:
  - React Testing Library (unit/integration)
  - Cypress (E2E)
- **Code Quality**:
  - ESLint with Next.js and TypeScript recommended rules
  - Prettier

## Getting Started

### Prerequisites

- Node.js 20 or higher
- npm

### Installation

```bash
npm install --legacy-peer-deps
```

### Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The app redirects to `/login` if not authenticated, then to `/organizations` or `/users` (by role) after sign-in.

**Backend**: Ensure the Inspectra API is running (default `http://localhost:8080`). Set `NEXT_PUBLIC_API_URL` if your API is elsewhere (e.g. in `.env.local`).

### Building for Production

```bash
npm run build
npm start
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm start` - Start production server
- `npm run lint` - Run ESLint
- `npm run lint:fix` - Fix ESLint errors
- `npm run format` - Format code with Prettier
- `npm run format:check` - Check code formatting
- `npm test` - Run Jest tests
- `npm run test:watch` - Run tests in watch mode
- `npm run test:coverage` - Run tests with coverage
- `npm run cypress:open` - Open Cypress test runner
- `npm run cypress:run` - Run Cypress tests headlessly
- `npm run type-check` - Run TypeScript type checking

## Backend integration

- The app talks to the Inspectra API (auth, organizations, users). Default base URL: `http://localhost:8080`.
- Set `NEXT_PUBLIC_API_URL` in `.env.local` if the API runs on another host/port (e.g. `NEXT_PUBLIC_API_URL=http://localhost:8080`).
- **Routes**: `/` → redirect to `/login` or (by role) `/organizations` / `/users`; `/login` → sign-in; `/organizations` (SUPER_ADMIN); `/users` (ADMIN + SUPER_ADMIN).

## Docker

Build and run with Docker:

```bash
docker build -t inspectra-frontend .
docker run -p 3000:3000 inspectra-frontend
```

## Project Structure

```
.
├── app/                    # Next.js app directory
│   ├── layout.tsx         # Root layout with providers
│   ├── page.tsx           # Home page
│   └── globals.css        # Global styles
├── components/            # React components
│   ├── ui/               # shadcn UI components
│   └── providers/        # Context providers
├── lib/                   # Utility functions and API clients
│   ├── api/              # API client and types
│   └── utils.ts          # Utility functions
├── __tests__/            # Jest tests
├── cypress/              # Cypress E2E tests
└── public/               # Static assets
```

## Testing

### Unit/Integration Tests (Jest + React Testing Library)

```bash
npm test
```

### E2E Tests (Cypress)

```bash
npm run cypress:open
```

## Code Quality

This project uses:

- **ESLint** with Next.js and TypeScript recommended rules for code linting
- **Prettier** for code formatting

Both are configured to work together. Run `npm run lint:fix` and `npm run format` before committing.
