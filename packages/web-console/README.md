# DevFoundry Web Console

A comprehensive React-based admin UI for DevFoundry.

## Features

- **Login/Authentication**: Secure access with token-based authentication
- **Dashboard**: Overview of system stats and recent tasks
- **Tasks**: Full task management with filtering, search, and detailed views
- **Project Configuration**: Manage repositories, tools, and skills
- **Appliance Health**: Monitor resources, services, and hardware

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Axios** - HTTP client
- **React Router** - Navigation
- **Zustand** - State management

## Prerequisites

- Node.js 18+ 
- PostgreSQL running
- DevFoundry API server running on port 3000

## Installation

```bash
cd packages/web-console
npm install
```

## Configuration

Copy `.env.example` to `.env.local` and update the configuration:

```bash
cp .env.example .env.local
```

## Development

```bash
npm run dev
```

The application will be available at `http://localhost:3001`

## Build for Production

```bash
npm run build
npm run preview
```

## API Integration

The web console connects to the DevFoundry API at `http://localhost:3000/api`.

### Endpoints Used

- `GET /api/tasks` - List tasks
- `POST /api/tasks` - Create task
- `GET /api/tasks/:id` - Get task details
- `PATCH /api/tasks/:id` - Update task
- `DELETE /api/tasks/:id` - Delete task
- `GET /api/tasks/:id/evidence` - Get task evidence
- `POST /api/tasks/:id/evidence` - Add evidence
- `GET /api/health` - Get appliance health

## Project Structure

```
packages/web-console/
├── src/
│   ├── components/
│   │   ├── ui/          # UI components (Button, Card, Badge, etc.)
│   │   ├── Navigation.tsx
│   │   └── ScrollToTop.tsx
│   ├── pages/           # Page components
│   ├── lib/
│   │   ├── api.ts       # API client
│   │   └── utils.ts     # Utility functions
│   ├── store/           # Zustand stores
│   ├── types.ts         # TypeScript types
│   ├── App.tsx          # Main app component
│   └── main.tsx         # Entry point
├── index.html
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
└── tsconfig.json
```

## Authentication

The web console uses token-based authentication. Upon successful login, the token is stored in `localStorage`.

## Task Management

Tasks support the following phases:
- Submitted → Qualified → Running → Validating → AwaitingReview → Completed
- Running → Paused (can resume)
- Any phase → Failed or Cancelled

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
