/**
 * Auth Service
 * Handles authentication logic: token generation, verification
 */

import jwt from 'jsonwebtoken';
import { config } from '../utils/config.js';
import type { User, JwtPayload, AuthSuccessResponse, AuthErrorResponse } from '../types/auth.js';
import { findUserByEmail, verifyPassword, toPublicUser } from './user.service.js';

/**
 * Generate JWT token for authenticated user
 */
export function generateToken(user: User): { token: string; expiresAt: Date } {
  const expiresAt = new Date(Date.now() + config.jwt.expiresInMs);

  const payload = {
    userId: user.id,
    email: user.email,
  };

  const token = jwt.sign(payload, config.jwt.secret, {
    expiresIn: config.jwt.expiresIn,
  });

  return { token, expiresAt };
}

/**
 * Verify and decode JWT token
 */
export function verifyToken(token: string): JwtPayload | null {
  try {
    const decoded = jwt.verify(token, config.jwt.secret) as JwtPayload;
    return decoded;
  } catch {
    return null;
  }
}

/**
 * Authenticate user with email and password
 */
export async function authenticateUser(
  email: string,
  password: string
): Promise<AuthSuccessResponse | AuthErrorResponse> {
  // Find user by email
  const user = await findUserByEmail(email);

  if (!user) {
    // Use generic message to prevent email enumeration
    return {
      success: false,
      error: {
        code: 'INVALID_CREDENTIALS',
        message: 'Invalid email or password',
      },
    };
  }

  // Verify password
  const isValidPassword = await verifyPassword(user, password);

  if (!isValidPassword) {
    return {
      success: false,
      error: {
        code: 'INVALID_CREDENTIALS',
        message: 'Invalid email or password',
      },
    };
  }

  // Generate token
  const { token, expiresAt } = generateToken(user);

  return {
    success: true,
    data: {
      user: toPublicUser(user),
      token,
      expiresAt: expiresAt.toISOString(),
    },
  };
}
