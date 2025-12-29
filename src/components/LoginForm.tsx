/**
 * LoginForm Component
 *
 * ============================================================================
 * API CONTRACT (Frontend Expectations)
 * ============================================================================
 *
 * ENDPOINT: POST /api/auth/login
 *
 * REQUEST BODY:
 * {
 *   "email": string,      // User's email address
 *   "password": string    // User's password (plaintext, HTTPS required)
 * }
 *
 * SUCCESS RESPONSE (200 OK):
 * {
 *   "token": string,      // JWT access token for Authorization header
 *   "user": {
 *     "id": string,       // User UUID
 *     "email": string,    // User email (echoed back)
 *     "name": string      // User display name
 *   }
 * }
 *
 * ERROR RESPONSE (400 Bad Request / 401 Unauthorized):
 * {
 *   "error": {
 *     "code": string,     // Machine-readable error code
 *     "message": string   // Human-readable error message
 *   }
 * }
 *
 * Expected Error Codes:
 * - "INVALID_CREDENTIALS" - Email/password combination is incorrect
 * - "VALIDATION_ERROR" - Request body failed validation
 * - "RATE_LIMITED" - Too many login attempts
 *
 * ============================================================================
 */

import React, { useState, useCallback, FormEvent, ChangeEvent } from 'react';

// Types - Frontend's expected contract
interface LoginCredentials {
  email: string;
  password: string;
}

interface User {
  id: string;
  email: string;
  name: string;
}

interface LoginSuccessResponse {
  token: string;
  user: User;
}

interface LoginErrorResponse {
  error: {
    code: string;
    message: string;
  };
}

type LoginResponse = LoginSuccessResponse | LoginErrorResponse;

// Type guard
function isLoginError(response: LoginResponse): response is LoginErrorResponse {
  return 'error' in response;
}

// Validation
interface ValidationErrors {
  email?: string;
  password?: string;
}

function validateCredentials(credentials: LoginCredentials): ValidationErrors {
  const errors: ValidationErrors = {};

  if (!credentials.email) {
    errors.email = 'Email is required';
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(credentials.email)) {
    errors.email = 'Please enter a valid email address';
  }

  if (!credentials.password) {
    errors.password = 'Password is required';
  } else if (credentials.password.length < 8) {
    errors.password = 'Password must be at least 8 characters';
  }

  return errors;
}

// Props
interface LoginFormProps {
  onSuccess?: (user: User, token: string) => void;
  onError?: (error: string) => void;
  apiBaseUrl?: string;
}

// Component
export function LoginForm({
  onSuccess,
  onError,
  apiBaseUrl = '',
}: LoginFormProps): React.ReactElement {
  // Form state
  const [credentials, setCredentials] = useState<LoginCredentials>({
    email: '',
    password: '',
  });
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // Handlers
  const handleInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>): void => {
      const { name, value } = event.target;
      setCredentials((prev) => ({ ...prev, [name]: value }));

      // Clear validation error for this field
      if (validationErrors[name as keyof ValidationErrors]) {
        setValidationErrors((prev) => ({ ...prev, [name]: undefined }));
      }

      // Clear API error on any input change
      if (apiError) {
        setApiError(null);
      }
    },
    [validationErrors, apiError]
  );

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>): Promise<void> => {
      event.preventDefault();

      // Validate
      const errors = validateCredentials(credentials);
      if (Object.keys(errors).length > 0) {
        setValidationErrors(errors);
        return;
      }

      setIsSubmitting(true);
      setApiError(null);

      try {
        // API call to POST /api/auth/login
        const response = await fetch(`${apiBaseUrl}/api/auth/login`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
        });

        const data: LoginResponse = await response.json();

        if (!response.ok || isLoginError(data)) {
          const errorMessage = isLoginError(data)
            ? data.error.message
            : 'An unexpected error occurred';
          setApiError(errorMessage);
          onError?.(errorMessage);
          return;
        }

        // Success
        onSuccess?.(data.user, data.token);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Network error. Please try again.';
        setApiError(message);
        onError?.(message);
      } finally {
        setIsSubmitting(false);
      }
    },
    [credentials, apiBaseUrl, onSuccess, onError]
  );

  return (
    <form onSubmit={handleSubmit} noValidate aria-label="Login form">
      <div className="login-form">
        {/* Email Field */}
        <div className="form-field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={credentials.email}
            onChange={handleInputChange}
            disabled={isSubmitting}
            aria-invalid={!!validationErrors.email}
            aria-describedby={validationErrors.email ? 'email-error' : undefined}
          />
          {validationErrors.email && (
            <span id="email-error" className="error-message" role="alert">
              {validationErrors.email}
            </span>
          )}
        </div>

        {/* Password Field */}
        <div className="form-field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={credentials.password}
            onChange={handleInputChange}
            disabled={isSubmitting}
            aria-invalid={!!validationErrors.password}
            aria-describedby={validationErrors.password ? 'password-error' : undefined}
          />
          {validationErrors.password && (
            <span id="password-error" className="error-message" role="alert">
              {validationErrors.password}
            </span>
          )}
        </div>

        {/* API Error */}
        {apiError && (
          <div className="api-error" role="alert">
            {apiError}
          </div>
        )}

        {/* Submit Button */}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Signing in...' : 'Sign In'}
        </button>
      </div>
    </form>
  );
}

export default LoginForm;
