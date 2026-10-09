# DevFoundry Web Console - Setup and Run Instructions

## Quick Start

```bash
# Navigate to web-console directory
cd packages/web-console

# Install dependencies
npm install

# Copy environment example
cp .env.example .env.local

# Start development server
npm run dev
```

## Complete Setup Guide

### 1. Prerequisites

Ensure the following are installed:
- **Node.js 18+** (https://nodejs.org/)
- **npm** (comes with Node.js)
- **PostgreSQL** (running on localhost:5432)
- **DevFoundry API** (running on port 3000)

### 2. Install Dependencies

```bash
cd /home/manimal/projects/dev-foundry/packages/web-console
npm install
```

### 3. Configure Environment

Create `.env.local` file:

```bash
cp .env.example .env.local
```

Edit `.env.local` with your configuration:

```env
API_BASE_URL=http://localhost:3000
DATABASE_URL=postgres://devfoundry:devfoundry@localhost:5432/devfoundry
ROUTEFORGE_URL=http://localhost:8001
CONTEXTFORGE_URL=http://localhost:8002
LANGFUSE_URL=http://localhost:3000
PORT=3000
NODE_ENV=development
```

### 4. Start the Development Server

```bash
npm run dev
```

The web console will be available at:
- **Development**: http://localhost:3001

### 5. Run in Production

```bash
# Build the application
npm run build

# Preview the production build
npm run preview
```

The production build will be available at http://localhost:4173

## API Server Requirements

The DevFoundry API must be running on port 3000 with the following endpoints:

### Required API Endpoints

#### Authentication
- `POST /api/auth/login` - Login endpoint (returns token)

#### Tasks
- `GET /api/tasks` - List tasks with optional filters
- `POST /api/tasks` - Create a new task
- `GET /api/tasks/:id` - Get task details
- `PATCH /api/tasks/:id` - Update task status
- `DELETE /api/tasks/:id` - Delete/cancel task
- `GET /api/tasks/:id/evidence` - Get task evidence
- `POST /api/tasks/:id/evidence` - Add evidence

#### Health
- `GET /health` - Health check
- `GET /api/health` - Appliance health (services, resources, hardware)

## Database Setup

Ensure PostgreSQL is running and the database is set up:

```sql
CREATE DATABASE devfoundry;
CREATE USER devfoundry WITH PASSWORD 'devfoundry';
GRANT ALL PRIVILEGES ON DATABASE devfoundry TO devfoundry;
```

## Architecture Overview

### Frontend Structure

```
packages/web-console/
├── src/
│   ├── components/
│   │   ├── ui/              # Reusable UI components
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Select.tsx
│   │   │   └── Textarea.tsx
│   │   ├── Navigation.tsx   # Top navigation bar
│   │   └── ScrollToTop.tsx  # Auto scroll to top on route change
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   ├── TasksPage.tsx
│   │   ├── TaskDetail.tsx
│   │   ├── ProjectConfig.tsx
│   │   └── ApplianceHealth.tsx
│   ├── lib/
│   │   ├── api.ts           # API client with interceptors
│   │   └── utils.ts         # Helper functions
│   ├── store/
│   │   └── taskStore.ts     # Zustand state management
│   ├── types.ts             # TypeScript type definitions
│   ├── App.tsx              # Main app component
│   └── main.tsx             # Entry point
├── index.html               # HTML template
├── vite.config.ts           # Vite configuration
├── tailwind.config.js       # Tailwind CSS config
├── postcss.config.js        # PostCSS configuration
└── tsconfig.json            # TypeScript configuration
```

### State Management

Uses **Zustand** for global state:

```typescript
import { useTaskStore } from './store/taskStore';

const { tasks, filters, setFilters } = useTaskStore();
```

### Component Library

All components use **Tailwind CSS** with custom design tokens:

- Primary colors: `bg-primary-600`, `text-primary-600`
- Dashboard colors: `bg-dashboard-bg`, `text-dashboard-text`
- Task phases: Color-coded badges for each phase

## Features

### 1. Login Page
- Email/password authentication
- Token stored in localStorage
- Protected routes

### 2. Dashboard
- Overview statistics (total, pending, in progress, completed)
- Recent tasks list
- Auto-refresh every 30 seconds

### 3. Tasks Page
- Task list with filtering
- Phase and status filters
- Search functionality
- Pagination
- Cancel, retry, and resume actions
- WebSocket integration for real-time updates

### 4. Task Detail Page
- Complete task information
- Execution details
- Skills and context
- Evidence and artifacts
- Action buttons (cancel, retry, resume)

### 5. Project Configuration
- Repository management
- Tool configuration
- Skills management
- Context status

### 6. Appliance Health
- Resource usage (CPU, memory, disk)
- GPU monitoring
- Service health (API, worker, database, etc.)
- Hardware profile display

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

## Development Commands

```bash
# Development mode
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Lint
npm run lint

# Type check
npx tsc --noEmit
```

## Troubleshooting

### Port Already in Use
If port 3001 is already in use, change it in `vite.config.ts`:

```typescript
server: {
  port: 3002,
  // ...
}
```

### API Connection Failed
Ensure the DevFoundry API is running on port 3000:

```bash
curl http://localhost:3000/health
```

### TypeScript Errors
Run type checking:

```bash
npx tsc --noEmit
```

## Customization

### Changing Colors
Edit `tailwind.config.js` to customize the color palette:

```javascript
colors: {
  primary: {
    50: '#eff6ff',
    600: '#3b82f6',
    700: '#1d4ed8',
  },
  // ...
}
```

### Adding New Pages
1. Create a new page component in `src/pages/`
2. Add a route in `App.tsx`
3. Add navigation link in `Navigation.tsx`

## Production Deployment

For production deployment, update the API endpoint in `.env.local`:

```env
API_BASE_URL=https://your-api-domain.com
```

Then build:

```bash
npm run build
```

The static files will be in `dist/` and can be served with any static file server.
