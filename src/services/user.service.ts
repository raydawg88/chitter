/**
 * User Service
 * Handles user data operations
 *
 * NOTE: This uses an in-memory store for development.
 * Replace with actual database (PostgreSQL, etc.) for production.
 */

import bcrypt from 'bcrypt';
import { config } from '../utils/config.js';
import type { User, PublicUser } from '../types/auth.js';

// In-memory user store (replace with database in production)
const users: Map<string, User> = new Map();

// Seed a test user for development
async function seedTestUser(): Promise<void> {
  const testEmail = 'test@example.com';
  if (!users.has(testEmail)) {
    const passwordHash = await bcrypt.hash('Password123', config.bcrypt.saltRounds);
    const now = new Date();
    users.set(testEmail, {
      id: 'user_001',
      email: testEmail,
      name: 'Test User',
      passwordHash,
      createdAt: now,
      updatedAt: now,
    });
    console.log('[DEV] Seeded test user: test@example.com / Password123');
  }
}

// Auto-seed in development
if (config.nodeEnv === 'development') {
  seedTestUser();
}

/**
 * Find user by email
 */
export async function findUserByEmail(email: string): Promise<User | null> {
  const normalizedEmail = email.toLowerCase().trim();
  return users.get(normalizedEmail) ?? null;
}

/**
 * Find user by ID
 */
export async function findUserById(id: string): Promise<User | null> {
  for (const user of users.values()) {
    if (user.id === id) {
      return user;
    }
  }
  return null;
}

/**
 * Create a new user
 */
export async function createUser(data: {
  email: string;
  password: string;
  name: string;
}): Promise<User> {
  const normalizedEmail = data.email.toLowerCase().trim();

  // Check if user already exists
  if (users.has(normalizedEmail)) {
    throw new Error('User with this email already exists');
  }

  const passwordHash = await bcrypt.hash(data.password, config.bcrypt.saltRounds);
  const now = new Date();

  const user: User = {
    id: `user_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
    email: normalizedEmail,
    name: data.name.trim(),
    passwordHash,
    createdAt: now,
    updatedAt: now,
  };

  users.set(normalizedEmail, user);
  return user;
}

/**
 * Verify user password
 */
export async function verifyPassword(user: User, password: string): Promise<boolean> {
  return bcrypt.compare(password, user.passwordHash);
}

/**
 * Convert User to PublicUser (strips sensitive fields)
 */
export function toPublicUser(user: User): PublicUser {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    createdAt: user.createdAt.toISOString(),
  };
}
