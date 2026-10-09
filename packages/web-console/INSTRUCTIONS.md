# DevFoundry Web Console - Complete Run Instructions

## Overview

This document provides complete instructions for running the DevFoundry Web Console, a React-based admin UI for managing DevFoundry tasks, projects, and system health.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DevFoundry Web Console                  │
│                  (React + Vite + Tailwind)                  │
│                     Port: 3001 (dev)                        │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP API
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   DevFoundry API                            │
│                 (Express + PostgreSQL)                      │
│                     Port: 3000                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌─────────────────────┐   ┌──────────────────────┐
│     PostgreSQL      │   │    RouteForge        │
│     (Database)      │   │    (Model Gateway)   │
│     Port: 5432      │   │    Port: 8001        │
└─────────────────────┘   └──────────────────────┘
```

## Prerequisites

Before running the web console, ensure:

1. **Node.js 18+** is installed
2. **PostgreSQL** is running
3. **DevFoundry API** is running on port 3000

### Check Prerequisites

```bash
# Check Node.js
node --version

# Check PostgreSQL
pg_isready -h localhost -p 5432

# Check API is running
curl http://localhost:3000/health
```

## Installation Steps

### Step 1: Navigate to Web Console Directory

```bash
cd /home/manimal/projects/dev-foundry/packages/web-console
```

### Step 2: Install Dependencies

```bash
npm install
```

This installs:
- React 18.2.0
- React Router DOM 6.22.0
- TypeScript 5.3.3
- Vite 5.1.0
- Tailwind CSS 3.4.1
- Axios 1.6.0
- And dependencies...

### Step 3: Configure Environment

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```env
# API Configuration
API_BASE_URL=http://localhost:3000

# Database Configuration  
DATABASE_URL=postgres://devfoundry:devfoundry@localhost:5432/devfoundry

# Model Gateway (RouteForge)
ROUTEFORGE_URL=http://localhost:8001

# Context Gateway
CONTEXTFORGE_URL=http://localhost:8002

# Langfuse
LANGFUSE_URL=http://localhost:3000

# Server Configuration
PORT=3000
NODE_ENV=development
```

### Step 4: Start Development Server

```bash
npm run dev
```

Expected output:
```
  VITE v5.1.0  ready in 345 ms

  ➜  Local:   http://localhost:3001/
  ➜  Network: use --host to expose
```

### Step 5: Access the Application

Open your browser and navigate to:
```
http://localhost:3001
```

Default credentials:
- Email: `admin@devfoundry.local`
- Password: `devfoundry`

## Running with Docker (Optional)

If you prefer Docker, you can run the API first:

```bash
# Build and run the API container
cd /home/manimal/projects/dev-foundry
docker-compose up -d api
```

Then start the web console:

```bash
cd packages/web-console
npm run dev
```

## Development Workflow

### Development Mode

```bash
npm run dev
```

Features:
- Hot module replacement (HMR)
- TypeScript type checking
- Source maps

### Production Build

```bash
# Build the application
npm run build

# Preview the production build
npm run preview
```

### Code Quality

```bash
# Type checking
npx tsc --noEmit

# Linting
npm run lint
```

## Testing the API Connection

Verify the API is accessible:

```bash
# Health check
curl http://localhost:3000/health

# Get tasks
curl http://localhost:3000/api/tasks

# Create a test task
curl -X POST http://localhost:3000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Test task",
    "projectId": "test-project",
    "userId": "test-user",
    "baseCommit": "abc123",
    "targetBranch": "main"
  }'
```

## Troubleshooting

### Error: Port 3001 already in use

**Solution:**
```bash
# Kill process on port 3001
lsof -ti:3001 | xargs kill -9

# Or change port in vite.config.ts
server: {
  port: 3002,
  // ...
}
```

### Error: Database connection failed

**Solution:**
1. Check PostgreSQL is running: `pg_isready -h localhost -p 5432`
2. Verify credentials in `.env.local`
3. Ensure database exists:
   ```sql
   CREATE DATABASE devfoundry;
   CREATE USER devfoundry WITH PASSWORD 'devfoundry';
   GRANT ALL PRIVILEGES ON DATABASE devfoundry TO devfoundry;
   ```

### Error: API not responding

**Solution:**
1. Ensure API is running: `curl http://localhost:3000/health`
2. Check API logs for errors
3. Verify API is listening on port 3000

### TypeScript Errors

**Solution:**
```bash
# Check for type errors
npx tsc --noEmit

# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

## Configuration Files

### vite.config.ts
```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:3000',
        changeOrigin: true,
      },
    },
  },
})
```

### tailwind.config.js
```javascript
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: { 600: '#3b82f6', 700: '#1d4ed8' },
        dashboard: {
          bg: '#f8fafc',
          card: '#ffffff',
          border: '#e2e8f0',
        },
      },
    },
  },
}
```

## Security Considerations

1. **Never commit `.env.local`** - It contains sensitive credentials
2. **Use HTTPS in production** - Add SSL certificate
3. **Validate API responses** - The web console validates all responses
4. **Token storage** - Tokens are stored in localStorage (consider sessionStorage for better security)

## Performance Optimization

The application includes:
- Code splitting with React.lazy()
- Automatic code minification in production
- Image optimization through Vite
- Tree shaking for unused dependencies

## Browser Support

- ✅ Chrome/Edge 90+
- ✅ Firefox 88+
- ✅ Safari 14+

## Monitoring

### Development
- View console logs in browser dev tools
- Check Vite dev server output

### Production
- Check browser console for errors
- Monitor network tab for API failures
- Review application logs

## Support

For issues:
1. Check the troubleshooting section
2. Review browser console for errors
3. Verify API is accessible
4. Check PostgreSQL connection

## Next Steps

After successfully running the web console:

1. **Explore the UI**: Navigate through all pages
2. **Create tasks**: Test task creation and management
3. **Configure projects**: Set up repositories and tools
4. **Monitor health**: Check appliance health metrics

## Advanced Configuration

### Environment Variables

```env
# Debug mode
VITE_DEBUG=true

# API timeout (ms)
VITE_API_TIMEOUT=30000

# WebSocket URL (for real-time updates)
VITE_WS_URL=ws://localhost:3000
```

### Customizing the Theme

Edit `tailwind.config.js` to customize:
- Primary colors
- Dashboard colors
- Border radius
- Spacing scale

### Adding New Features

1. Create component in `src/components/`
2. Add TypeScript types in `src/types.ts`
3. Add API calls in `src/lib/api.ts`
4. Add route in `src/App.tsx`
5. Add navigation link in `src/components/Navigation.tsx`

## Version History

- **v0.1.0** (Current)
  - Initial release
  - Tasks management
  - Project configuration
  - Appliance health monitoring
  - Authentication

## License

DevFoundry Web Console - Internal use only

## Credits

Built with:
- React 18.2.0
- TypeScript 5.3.3
- Vite 5.1.0
- Tailwind CSS 3.4.1
- React Router 6.22.0
- Zustand 4.4.7
- Axios 1.6.0
