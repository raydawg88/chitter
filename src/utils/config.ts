/**
 * Application Configuration
 * Centralized config with environment variable validation
 */

function requireEnv(key: string, defaultValue?: string): string {
  const value = process.env[key] ?? defaultValue;
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
}

export const config = {
  port: parseInt(process.env.PORT ?? '3000', 10),
  nodeEnv: process.env.NODE_ENV ?? 'development',

  jwt: {
    secret: requireEnv('JWT_SECRET', 'dev-secret-change-in-production'),
    expiresIn: '24h',
    expiresInMs: 24 * 60 * 60 * 1000, // 24 hours in milliseconds
  },

  bcrypt: {
    saltRounds: 12,
  },
} as const;

// Warn in development if using default secret
if (config.nodeEnv === 'development' && config.jwt.secret === 'dev-secret-change-in-production') {
  console.warn('[WARN] Using default JWT secret - DO NOT use in production');
}
