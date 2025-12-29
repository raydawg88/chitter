/**
 * Auth Types
 * Defines the shape of authentication requests, responses, and user data
 */

export interface User {
  id: string;
  email: string;
  name: string;
  passwordHash: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface PublicUser {
  id: string;
  email: string;
  name: string;
  createdAt: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthSuccessResponse {
  success: true;
  data: {
    user: PublicUser;
    token: string;
    expiresAt: string;
  };
}

export interface AuthErrorResponse {
  success: false;
  error: {
    code: 'INVALID_CREDENTIALS' | 'VALIDATION_ERROR' | 'INTERNAL_ERROR' | 'USER_NOT_FOUND';
    message: string;
  };
}

export type AuthResponse = AuthSuccessResponse | AuthErrorResponse;

export interface JwtPayload {
  userId: string;
  email: string;
  iat: number;
  exp: number;
}
