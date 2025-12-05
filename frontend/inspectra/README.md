# Inspectra Frontend

A modern Next.js application skeleton with TypeScript, Tailwind CSS, TanStack Query, Zod, and shadcn UI components.

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

Open [http://localhost:3000](http://localhost:3000) in your browser.

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

## Backend Integration

The backend FastAPI server is not ready yet. When it's available:

1. Generate TypeScript types from OpenAPI schema:

   ```bash
   npx openapi-typescript http://localhost:8000/openapi.json -o ./lib/api/types.ts
   ```

2. Uncomment the fetch call in `lib/api/client.ts` and remove the mock return.

3. Set the `NEXT_PUBLIC_API_URL` environment variable to your backend URL.

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
