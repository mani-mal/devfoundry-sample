# DevFoundry Docker Deployment

This directory contains Docker Compose configurations for deploying DevFoundry.

## Compact Profile

The Compact profile is designed for single-host deployments with all services running in containers on one machine.

### Services

- **PostgreSQL**: Primary database with DevFoundry schema
- **DevFoundry API**: REST API server (port 3000)
- **DevFoundry Worker**: Background task processor
- **RouteForge**: Model gateway (port 8080)
- **ContextForge**: MCP gateway (port 3001)
- **Langfuse**: OSS telemetry UI (port 3000)
- **Langfuse PostgreSQL**: Dedicated database for Langfuse

### Quick Start

```bash
# Copy example environment file
cp .env.example .env

# Start all services
docker-compose -f docker-compose compact.yml up -d

# View logs
docker-compose -f docker-compose compact.yml logs -f

# Stop services
docker-compose -f docker-compose compact.yml down
```

### Configuration

Environment variables are loaded from `.env` file:

```env
POSTGRES_PASSWORD=your_secure_password
DATABASE_URL=postgres://devfoundry:password@postgres:5432/devfoundry
ROUTEFORGE_URL=http://routeforge:8080
CONTEXTFORGE_URL=http://context-forge:3001
LANGFUSE_URL=http://langfuse:3000
```

### Volumes

- `postgres_data`: PostgreSQL data persistence
- `langfuse_postgres_data`: Langfuse database persistence
- `/var/data/evidence`: Evidence storage (local filesystem)

### Ports

| Service | Port | Description |
|---------|------|-------------|
| DevFoundry API | 3000 | Main API |
| RouteForge | 8080 | Model gateway |
| ContextForge | 3001 | MCP gateway |
| Langfuse UI | 3000 | Telemetry dashboard |

## Health Checks

All services have health checks configured:

```bash
# Check service health
docker-compose -f docker-compose compact.yml ps
```

## Monitoring

Access the web console at `http://localhost:3000`

## Logs

```bash
# View all logs
docker-compose -f docker-compose compact.yml logs

# Follow logs
docker-compose -f docker-compose compact.yml logs -f

# View specific service logs
docker-compose -f docker-compose compact.yml logs api
```

## Updates

```bash
# Pull latest images
docker-compose -f docker-compose compact.yml pull

# Restart services
docker-compose -f docker-compose compact.yml up -d

# View update status
docker-compose -f docker-compose compact.yml ps
```

## Backup

```bash
# Backup PostgreSQL data
docker exec -t devfoundry-postgres pg_dump -U devfoundry devfoundry > backup.sql
```

## Restore

```bash
# Restore from backup
cat backup.sql | docker exec -i devfoundry-postgres psql -U devfoundry -d devfoundry
```

## Troubleshooting

### Service not starting

```bash
# Check logs
docker-compose -f docker-compose compact.yml logs <service>

# Rebuild service
docker-compose -f docker-compose compact.yml build --no-cache <service>
```

### Database connection failed

```bash
# Verify database is ready
docker-compose -f docker-compose compact.yml exec postgres pg_isready -U devfoundry

# Restart database
docker-compose -f docker-compose compact.yml restart postgres
```

### Port already in use

```bash
# Find process using port
lsof -i :3000

# Or change port in docker-compose compact.yml
```

## Production Deployment

For production use:

1. Use strong passwords for all services
2. Enable TLS/SSL for database connections
3. Configure proper network policies
4. Set up monitoring and alerting
5. Implement regular backups
6. Use secrets management (Docker secrets, HashiCorp Vault)

## Support

For issues and questions, please check the main DevFoundry documentation.
