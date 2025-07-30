/**
 * Error handling utilities for graceful error management
 * Provides centralized error handling, retry mechanisms, and user-friendly error messages
 */

/**
 * Error types for categorizing different kinds of errors
 */
export const ErrorTypes = {
  NETWORK: 'NETWORK',
  DATA_PARSING: 'DATA_PARSING',
  VALIDATION: 'VALIDATION',
  COMPONENT: 'COMPONENT',
  UNKNOWN: 'UNKNOWN'
};

/**
 * Error severity levels
 */
export const ErrorSeverity = {
  LOW: 'LOW',
  MEDIUM: 'MEDIUM',
  HIGH: 'HIGH',
  CRITICAL: 'CRITICAL'
};

/**
 * Custom error class with additional context
 */
export class AppError extends Error {
  constructor(message, type = ErrorTypes.UNKNOWN, severity = ErrorSeverity.MEDIUM, context = {}) {
    super(message);
    this.name = 'AppError';
    this.type = type;
    this.severity = severity;
    this.context = context;
    this.timestamp = new Date().toISOString();
    
    // Maintain proper stack trace
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, AppError);
    }
  }

  /**
   * Convert error to JSON for logging
   * @returns {Object} JSON representation of error
   */
  toJSON() {
    return {
      name: this.name,
      message: this.message,
      type: this.type,
      severity: this.severity,
      context: this.context,
      timestamp: this.timestamp,
      stack: this.stack
    };
  }
}

/**
 * Error handler class for centralized error management
 */
export class ErrorHandler {
  constructor() {
    this.errorListeners = new Set();
    this.errorLog = [];
    this.maxLogSize = 100;
    this.retryAttempts = new Map();
    this.maxRetries = 3;
  }

  /**
   * Handle an error with appropriate response
   * @param {Error|AppError} error - The error to handle
   * @param {Object} options - Handling options
   * @returns {Object} Error handling result
   */
  handleError(error, options = {}) {
    const {
      showToUser = true,
      logError = true,
      retryable = false,
      context = {}
    } = options;

    // Convert to AppError if needed
    const appError = error instanceof AppError ? error : this.createAppError(error, context);
    
    // Log the error
    if (logError) {
      this.logError(appError);
    }

    // Notify listeners
    this.notifyListeners(appError);

    // Show user-friendly message if requested
    if (showToUser) {
      this.showUserError(appError);
    }

    return {
      error: appError,
      userMessage: this.getUserMessage(appError),
      canRetry: retryable && this.canRetry(appError),
      retryCount: this.getRetryCount(appError)
    };
  }

  /**
   * Create AppError from generic error
   * @param {Error} error - Original error
   * @param {Object} context - Additional context
   * @returns {AppError} Converted error
   */
  createAppError(error, context = {}) {
    let type = ErrorTypes.UNKNOWN;
    let severity = ErrorSeverity.MEDIUM;

    // Categorize error based on message or type
    if (error.name === 'TypeError' || error.name === 'ReferenceError') {
      type = ErrorTypes.COMPONENT;
      severity = ErrorSeverity.HIGH;
    } else if (error.message.includes('fetch') || error.message.includes('network')) {
      type = ErrorTypes.NETWORK;
      severity = ErrorSeverity.MEDIUM;
    } else if (error.message.includes('JSON') || error.message.includes('parse')) {
      type = ErrorTypes.DATA_PARSING;
      severity = ErrorSeverity.MEDIUM;
    }

    return new AppError(error.message, type, severity, {
      originalError: error.name,
      ...context
    });
  }

  /**
   * Log error to internal log and console
   * @param {AppError} error - Error to log
   */
  logError(error) {
    // Add to internal log
    this.errorLog.push(error.toJSON());
    
    // Maintain log size
    if (this.errorLog.length > this.maxLogSize) {
      this.errorLog.shift();
    }

    // Console logging based on severity
    switch (error.severity) {
      case ErrorSeverity.CRITICAL:
        console.error('CRITICAL ERROR:', error);
        break;
      case ErrorSeverity.HIGH:
        console.error('ERROR:', error);
        break;
      case ErrorSeverity.MEDIUM:
        console.warn('WARNING:', error);
        break;
      case ErrorSeverity.LOW:
        console.info('INFO:', error);
        break;
    }
  }

  /**
   * Get user-friendly error message
   * @param {AppError} error - Error to get message for
   * @returns {string} User-friendly message
   */
  getUserMessage(error) {
    switch (error.type) {
      case ErrorTypes.NETWORK:
        return 'Unable to load data. Please check your internet connection and try again.';
      case ErrorTypes.DATA_PARSING:
        return 'There was a problem processing the data. Please try refreshing the page.';
      case ErrorTypes.VALIDATION:
        return 'Please check your input and try again.';
      case ErrorTypes.COMPONENT:
        return 'Something went wrong. Please refresh the page and try again.';
      default:
        return 'An unexpected error occurred. Please try again.';
    }
  }

  /**
   * Show error to user (can be overridden for custom UI)
   * @param {AppError} error - Error to show
   */
  showUserError(error) {
    // Default implementation - can be overridden
    const message = this.getUserMessage(error);
    
    // Try to show in a toast or notification if available
    if (typeof window !== 'undefined' && window.showNotification) {
      window.showNotification(message, 'error');
    } else {
      console.error('User Error:', message);
    }
  }

  /**
   * Add error listener
   * @param {Function} listener - Error listener function
   */
  addErrorListener(listener) {
    this.errorListeners.add(listener);
  }

  /**
   * Remove error listener
   * @param {Function} listener - Error listener function
   */
  removeErrorListener(listener) {
    this.errorListeners.delete(listener);
  }

  /**
   * Notify all error listeners
   * @param {AppError} error - Error to notify about
   */
  notifyListeners(error) {
    this.errorListeners.forEach(listener => {
      try {
        listener(error);
      } catch (listenerError) {
        console.error('Error in error listener:', listenerError);
      }
    });
  }

  /**
   * Check if error can be retried
   * @param {AppError} error - Error to check
   * @returns {boolean} Whether error can be retried
   */
  canRetry(error) {
    const retryCount = this.getRetryCount(error);
    return retryCount < this.maxRetries && (
      error.type === ErrorTypes.NETWORK ||
      error.type === ErrorTypes.DATA_PARSING
    );
  }

  /**
   * Get retry count for error
   * @param {AppError} error - Error to get count for
   * @returns {number} Retry count
   */
  getRetryCount(error) {
    const key = `${error.type}-${error.message}`;
    return this.retryAttempts.get(key) || 0;
  }

  /**
   * Increment retry count for error
   * @param {AppError} error - Error to increment count for
   */
  incrementRetryCount(error) {
    const key = `${error.type}-${error.message}`;
    const currentCount = this.getRetryCount(error);
    this.retryAttempts.set(key, currentCount + 1);
  }

  /**
   * Reset retry count for error
   * @param {AppError} error - Error to reset count for
   */
  resetRetryCount(error) {
    const key = `${error.type}-${error.message}`;
    this.retryAttempts.delete(key);
  }

  /**
   * Get error log
   * @returns {Array} Array of logged errors
   */
  getErrorLog() {
    return [...this.errorLog];
  }

  /**
   * Clear error log
   */
  clearErrorLog() {
    this.errorLog = [];
  }

  /**
   * Get error statistics
   * @returns {Object} Error statistics
   */
  getErrorStats() {
    const stats = {
      total: this.errorLog.length,
      byType: {},
      bySeverity: {},
      recent: this.errorLog.slice(-10)
    };

    this.errorLog.forEach(error => {
      stats.byType[error.type] = (stats.byType[error.type] || 0) + 1;
      stats.bySeverity[error.severity] = (stats.bySeverity[error.severity] || 0) + 1;
    });

    return stats;
  }
}

/**
 * Retry utility with exponential backoff
 */
export class RetryManager {
  constructor(options = {}) {
    this.maxRetries = options.maxRetries || 3;
    this.baseDelay = options.baseDelay || 1000;
    this.maxDelay = options.maxDelay || 10000;
    this.backoffFactor = options.backoffFactor || 2;
  }

  /**
   * Retry an async operation with exponential backoff
   * @param {Function} operation - Async operation to retry
   * @param {Object} options - Retry options
   * @returns {Promise} Operation result
   */
  async retry(operation, options = {}) {
    const {
      maxRetries = this.maxRetries,
      onRetry = () => {},
      shouldRetry = () => true
    } = options;

    let lastError;
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = error;
        
        if (attempt === maxRetries || !shouldRetry(error, attempt)) {
          throw error;
        }

        const delay = Math.min(
          this.baseDelay * Math.pow(this.backoffFactor, attempt),
          this.maxDelay
        );

        onRetry(error, attempt + 1, delay);
        await this.delay(delay);
      }
    }

    throw lastError;
  }

  /**
   * Delay utility
   * @param {number} ms - Milliseconds to delay
   * @returns {Promise} Delay promise
   */
  delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

/**
 * Global error handler instance
 */
export const errorHandler = new ErrorHandler();

/**
 * Global retry manager instance
 */
export const retryManager = new RetryManager();

/**
 * Utility functions for common error scenarios
 */

/**
 * Handle async operation with error handling and retry
 * @param {Function} operation - Async operation
 * @param {Object} options - Options
 * @returns {Promise} Operation result
 */
export async function withErrorHandling(operation, options = {}) {
  const {
    retryable = false,
    showToUser = true,
    context = {}
  } = options;

  try {
    if (retryable) {
      return await retryManager.retry(operation, {
        shouldRetry: (error) => {
          const appError = error instanceof AppError ? error : errorHandler.createAppError(error);
          return errorHandler.canRetry(appError);
        },
        onRetry: (error, attempt, delay) => {
          const appError = error instanceof AppError ? error : errorHandler.createAppError(error);
          errorHandler.incrementRetryCount(appError);
          console.info(`Retrying operation (attempt ${attempt}) after ${delay}ms:`, error.message);
        }
      });
    } else {
      return await operation();
    }
  } catch (error) {
    const result = errorHandler.handleError(error, {
      showToUser,
      retryable,
      context
    });
    
    throw result.error;
  }
}

/**
 * Create a safe async function that handles errors
 * @param {Function} fn - Async function to wrap
 * @param {Object} options - Error handling options
 * @returns {Function} Safe async function
 */
export function createSafeAsync(fn, options = {}) {
  return async (...args) => {
    try {
      return await withErrorHandling(() => fn(...args), options);
    } catch (error) {
      // Error has already been handled, return null or default value
      return options.defaultValue || null;
    }
  };
}

/**
 * Validate data and throw validation error if invalid
 * @param {*} data - Data to validate
 * @param {Function} validator - Validation function
 * @param {string} message - Error message
 */
export function validateData(data, validator, message = 'Validation failed') {
  if (!validator(data)) {
    throw new AppError(message, ErrorTypes.VALIDATION, ErrorSeverity.MEDIUM, { data });
  }
}