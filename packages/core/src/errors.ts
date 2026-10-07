export class DevFoundryError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'DevFoundryError';
  }
}

export class ValidationError extends DevFoundryError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'VALIDATION_ERROR', details);
    this.name = 'ValidationError';
  }
}

export class AuthorizationError extends DevFoundryError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'AUTHORIZATION_ERROR', details);
    this.name = 'AuthorizationError';
  }
}

export class NotFoundError extends DevFoundryError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'NOT_FOUND', details);
    this.name = 'NotFoundError';
  }
}

export class ConflictError extends DevFoundryError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'CONFLICT', details);
    this.name = 'ConflictError';
  }
}

export class InternalError extends DevFoundryError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'INTERNAL_ERROR', details);
    this.name = 'InternalError';
  }
}

export class GatewayError extends DevFoundryError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'GATEWAY_ERROR', details);
    this.name = 'GatewayError';
  }
}

export class WorkspaceError extends DevFoundryError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'WORKSPACE_ERROR', details);
    this.name = 'WorkspaceError';
  }
}

export class CapacityError extends DevFoundryError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 'CAPACITY_ERROR', details);
    this.name = 'CapacityError';
  }
}
