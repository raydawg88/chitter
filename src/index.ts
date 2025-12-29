/**
 * Chitter API Server
 * Main entry point
 */

import express from 'express';
import { config } from './utils/config.js';
import authRoutes from './routes/auth.routes.js';
import { errorHandler } from './middleware/errorHandler.js';

const app = express();

// Middleware
app.use(express.json());

// CORS headers (configure properly for production)
app.use((_req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  next();
});

// Health check
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Routes
app.use('/api/auth', authRoutes);

// Error handling (must be last)
app.use(errorHandler);

// Start server
app.listen(config.port, () => {
  console.log(`
========================================
  Chitter API Server
========================================
  Port:        ${config.port}
  Environment: ${config.nodeEnv}

  Endpoints:
    POST /api/auth/login     - Login
    POST /api/auth/register  - Register
    GET  /api/auth/me        - Current user
    GET  /health             - Health check
========================================
`);
});

export default app;
