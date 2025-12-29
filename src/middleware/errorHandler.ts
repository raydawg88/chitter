/**
 * Error Handling Middleware
 * Centralizes error responses for consistency
 */

import type { Request, Response, NextFunction } from 'express';
import { ZodError } from 'zod';
import type { AuthErrorResponse } from '../types/auth.js';

export class AppError extends Error {
  constructor(
    public statusCode: number,
    public code: AuthErrorResponse['error']['code'],
    message: string
  ) {
    super(message);
    this.name = 'AppError';
  }
}

export function errorHandler(
  err: Error,
  _req: Request,
  res: Response,
  _next: NextFunction
): void {
  console.error('[ERROR]', err);

  // Handle Zod validation errors
  if (err instanceof ZodError) {
    const firstError = err.errors[0];
    const response: AuthErrorResponse = {
      success: false,
      error: {
        code: 'VALIDATION_ERROR',
        message: firstError?.message ?? 'Validation failed',
      },
    };
    res.status(400).json(response);
    return;
  }

  // Handle custom app errors
  if (err instanceof AppError) {
    const response: AuthErrorResponse = {
      success: false,
      error: {
        code: err.code,
        message: err.message,
      },
    };
    res.status(err.statusCode).json(response);
    return;
  }

  // Handle unknown errors
  const response: AuthErrorResponse = {
    success: false,
    error: {
      code: 'INTERNAL_ERROR',
      message: 'An unexpected error occurred',
    },
  };
  res.status(500).json(response);
}
