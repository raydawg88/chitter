/**
 * Auth Routes
 *
 * POST /api/auth/login     - Authenticate user, returns JWT
 * POST /api/auth/register  - Create new user account
 * GET  /api/auth/me        - Get current authenticated user
 */

import { Router, type Request, type Response, type NextFunction } from 'express';
import { loginSchema, registerSchema } from '../utils/validation.js';
import { authenticateUser, generateToken } from '../services/auth.service.js';
import { createUser, findUserByEmail, toPublicUser } from '../services/user.service.js';
import { requireAuth } from '../middleware/auth.js';
import type { AuthSuccessResponse, AuthErrorResponse } from '../types/auth.js';

const router = Router();

/**
 * POST /api/auth/login
 * Authenticate user with email and password
 */
router.post('/login', async (req: Request, res: Response, next: NextFunction): Promise<void> => {
  try {
    // Validate request body
    const validated = loginSchema.parse(req.body);

    // Attempt authentication
    const result = await authenticateUser(validated.email, validated.password);

    if (result.success) {
      res.status(200).json(result);
    } else {
      res.status(401).json(result);
    }
  } catch (error) {
    next(error);
  }
});

/**
 * POST /api/auth/register
 * Create new user account
 */
router.post('/register', async (req: Request, res: Response, next: NextFunction): Promise<void> => {
  try {
    // Validate request body
    const validated = registerSchema.parse(req.body);

    // Check if email already exists
    const existingUser = await findUserByEmail(validated.email);
    if (existingUser) {
      const response: AuthErrorResponse = {
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'An account with this email already exists',
        },
      };
      res.status(409).json(response);
      return;
    }

    // Create user
    const user = await createUser({
      email: validated.email,
      password: validated.password,
      name: validated.name,
    });

    // Generate token for immediate login
    const { token, expiresAt } = generateToken(user);

    const response: AuthSuccessResponse = {
      success: true,
      data: {
        user: toPublicUser(user),
        token,
        expiresAt: expiresAt.toISOString(),
      },
    };

    res.status(201).json(response);
  } catch (error) {
    next(error);
  }
});

/**
 * GET /api/auth/me
 * Get current authenticated user
 * Requires: Authorization: Bearer <token>
 */
router.get('/me', requireAuth, (req: Request, res: Response): void => {
  // req.user is guaranteed to exist after requireAuth middleware
  const user = req.user!;

  const response: AuthSuccessResponse = {
    success: true,
    data: {
      user: toPublicUser(user),
      token: '', // Not returning token on /me endpoint
      expiresAt: '', // Not applicable for /me
    },
  };

  // Return just the user for /me endpoint
  res.status(200).json({
    success: true,
    data: {
      user: toPublicUser(user),
    },
  });
});

export default router;
