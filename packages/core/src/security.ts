import { Identity, IdentityType, Task, ToolPermission } from './types';
import { DevFoundryError, AuthorizationError, InternalError } from './errors';

export interface PermissionCheck {
  allowed: boolean;
  reason?: string;
}

export interface ServiceToken {
  token: string;
  expiresAt: Date;
  scopes: string[];
  identity: Identity;
}

export interface SPIFFEConfig {
  trustDomain: string;
  bundleEndpoint: string;
  mTLSEnabled: boolean;
}

export class SecurityService {
  private oidcIssuer?: string;
  private audience?: string;
  private spiiffeConfig?: SPIFFEConfig;

  constructor(config?: {
    oidcIssuer?: string;
    audience?: string;
    spiiffe?: SPIFFEConfig;
  }) {
    if (config?.oidcIssuer) {
      this.oidcIssuer = config.oidcIssuer;
    }
    if (config?.audience) {
      this.audience = config.audience;
    }
    if (config?.spiiffe) {
      this.spiiffeConfig = config.spiiffe;
    }
  }

  validateToken(token: string): Identity | null {
    try {
      const payload = this.decodeToken(token);
      return this.buildIdentityFromPayload(payload);
    } catch (error) {
      return null;
    }
  }

  decodeToken(token: string): Record<string, unknown> {
    const parts = token.split('.');
    if (parts.length !== 3) {
      throw new Error('Invalid token format');
    }

    const payload = JSON.parse(atob(parts[1]));
    return payload;
  }

  buildIdentityFromPayload(payload: Record<string, unknown>): Identity {
    const identityType = typeof payload.iss === 'string' && payload.iss.includes('/services/')
      ? 'service'
      : typeof payload.iss === 'string' && payload.iss.includes('/tasks/')
      ? 'task'
      : 'user';

    return {
      id: typeof payload.sub === 'string' ? payload.sub : typeof payload.id === 'string' ? payload.id : 'unknown',
      type: identityType as IdentityType,
      tenantId: typeof payload.tenant_id === 'string' ? payload.tenant_id : typeof payload.tenantId === 'string' ? payload.tenantId : 'unknown',
      projectId: typeof payload.project_id === 'string' ? payload.project_id : typeof payload.projectId === 'string' ? payload.projectId : undefined,
      scopes: Array.isArray(payload.scopes) ? payload.scopes : Array.isArray(payload.roles) ? payload.roles : [],
      credentials: {
        token: typeof payload.token === 'string' ? payload.token : 'token',
        service: typeof payload.service === 'string' ? payload.service : undefined,
        spiiffe: typeof payload.spiffe_id === 'string' ? payload.spiffe_id : undefined,
      },
    };
  }

  checkPermission(identity: Identity, resource: string, action: string): PermissionCheck {
    const requiredScopes = this.deriveRequiredScopes(resource, action);

    const hasPermission = requiredScopes.every((scope) =>
      identity.scopes.some((identityScope) => this.scopeMatches(identityScope, scope))
    );

    if (!hasPermission) {
      return {
        allowed: false,
        reason: `Missing required scope for ${action} on ${resource}`,
      };
    }

    return { allowed: true };
  }

  deriveRequiredScopes(resource: string, action: string): string[] {
    const resourceParts = resource.split(':');
    const resourceType = resourceParts[0];

    const scopeBase = `devfoundry:${resourceType}`;

    switch (action) {
      case 'read':
        return [`${scopeBase}:read`, `${scopeBase}:*`, `${scopeBase}`];
      case 'write':
        return [`${scopeBase}:write`, `${scopeBase}:*`, `${scopeBase}`];
      case 'delete':
        return [`${scopeBase}:delete`, `${scopeBase}:*`, `${scopeBase}`];
      case 'admin':
        return [`${scopeBase}:admin`, `${scopeBase}:*`];
      default:
        return [`${scopeBase}:${action}`, `${scopeBase}:*`];
    }
  }

  scopeMatches(identityScope: string, requiredScope: string): boolean {
    const identityParts = identityScope.split(':');
    const requiredParts = requiredScope.split(':');

    if (identityParts.length < requiredParts.length) {
      return false;
    }

    for (let i = 0; i < requiredParts.length; i++) {
      if (identityParts[i] !== requiredParts[i] && requiredParts[i] !== '*') {
        return false;
      }
    }

    return true;
  }

  generateServiceToken(identity: Identity, ttl?: number): ServiceToken {
    const expiresAt = new Date(Date.now() + (ttl || 3600000));
    
    const payload = {
      sub: identity.id,
      iss: '/services/devfoundry',
      iat: Date.now(),
      exp: expiresAt.getTime(),
      tenant_id: identity.tenantId,
      project_id: identity.projectId,
      scopes: identity.scopes,
      service: identity.credentials.service,
      spiffe_id: identity.credentials.spiiffe,
    };

    const token = this.encodeToken(payload);
    const scopes = identity.scopes;

    return {
      token,
      expiresAt,
      scopes,
      identity,
    };
  }

  encodeToken(payload: Record<string, unknown>): string {
    const header = { alg: 'HS256', typ: 'JWT' };
    const encodedHeader = btoa(JSON.stringify(header));
    const encodedPayload = btoa(JSON.stringify(payload));
    const signature = this.signToken(encodedHeader, encodedPayload);

    return `${encodedHeader}.${encodedPayload}.${signature}`;
  }

  signToken(header: string, payload: string): string {
    const message = `${header}.${payload}`;
    let hash = 0;
    for (let i = 0; i < message.length; i++) {
      const char = message.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString(16);
  }

  generateSPIFFEIdentity(task: Task): string {
    if (!this.spiiffeConfig) {
      throw new InternalError('SPIFFE not configured');
    }

    return `spiffe://${this.spiiffeConfig.trustDomain}/ns/${task.tenantId}/sid/${task.id}`;
  }

  verifySPIFFEIdentity(identity: Identity): boolean {
    if (!this.spiiffeConfig || !identity.credentials.spiiffe) {
      return false;
    }

    const expectedPrefix = `spiffe://${this.spiiffeConfig.trustDomain}`;
    return identity.credentials.spiiffe.startsWith(expectedPrefix);
  }

  checkTaskIdentity(task: Task, userId: string): boolean {
    return task.userId === userId || task.tenantId === userId;
  }

  checkToolPermission(task: Task, toolId: string): boolean {
    return task.toolPermissions.some(
      (perm) =>
        perm.toolId === toolId &&
        (perm.scopes.includes('*') || this.hasRequiredScopes(task, perm.scopes))
    );
  }

  private hasRequiredScopes(task: Task, requiredScopes: string[]): boolean {
    return requiredScopes.some((scope) => {
      if (scope === '*') {
        return true;
      }
      return task.toolPermissions.some((perm) =>
        perm.scopes.includes(scope)
      );
    });
  }
}
