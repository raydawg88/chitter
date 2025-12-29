/**
 * Auth Middleware
 * Protects routes requiring authentication
 */

import type { Request, Response, NextFunction } from 'express';
import { verifyToken } from '../services/auth.service.js';
import { findUserById } from '../services/user.service.js';
import type { User, AuthErrorResponse } from '../types/auth.js';

// Extend Express Request to include authenticated user
declare global {
  namespace Express {
    interface Request {
      user?: User;
    }
  }
}

/**
 * Middleware to require valid JWT authentication
 * Extracts token from Authorization header (Bearer scheme)
 */
export async function requireAuth(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  const authHeader = req.headers.authorization;

  if (!authHeader) {
    const response: AuthErrorResponse = {
      success: false,
      error: {
        code: 'INVALID_CREDENTIALS',
        message: 'Authorization header required',
      },
    };
    res.status(401).json(response);
    return;
  }

  // Expect "Bearer <token>" format
  const parts = authHeader.split(' ');
  if (parts.length !== 2 || parts[0] !== 'Bearer') {
    const response: AuthErrorResponse = {
      success: false,
      error: {
        code: 'INVALID_CREDENTIALS',
        message: 'Invalid authorization format. Use: Bearer <token>',
      },
    };
    res.status(401).json(response);
    return;
  }

  const token = parts[1];
  const decoded = verifyToken(token);

  if (!decoded) {
    const response: AuthErrorResponse = {
      success: false,
      error: {
        code: 'INVALID_CREDENTIALS',
        message: 'Invalid or expired token',
      },
    };
    res.status(401).json(response);
    return;
  }

  // Fetch full user from database
  const user = await findUserById(decoded.userId);

  if (!user) {
    const response: AuthErrorResponse = {
      success: false,
      error: {
        code: 'USER_NOT_FOUND',
        message: 'User no longer exists',
      },
    };
    res.status(401).json(response);
    return;
  }

  // Attach user to request for downstream handlers
  req.user = user;
  next();
}
