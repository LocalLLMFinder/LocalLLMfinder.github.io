/**
 * Utility functions for formatting data in the GGUF Model Index
 */

/**
 * Convert bytes to human-readable format (GB, MB, KB)
 * @param {number} bytes - File size in bytes
 * @param {number} decimals - Number of decimal places (default: 1)
 * @returns {string} Formatted size string (e.g., "4.2 GB", "512 MB")
 */
export function formatFileSize(bytes, decimals = 1) {
  if (!bytes || bytes === 0) return '0 B';
  
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  
  // Remove unnecessary decimal places for whole numbers
  const formatted = value % 1 === 0 ? value.toString() : value.toFixed(dm);
  
  return formatted + ' ' + sizes[i];
}

/**
 * Generate searchable text for a model by combining relevant fields
 * @param {Object} model - Model object with metadata
 * @returns {string} Combined searchable text
 */
export function generateSearchableText(model) {
  const searchFields = [
    model.name,
    model.modelId,
    model.filename,
    model.quantization,
    model.architecture,
    model.family,
    model.sizeFormatted,
    ...(model.tags || [])
  ];
  
  return searchFields
    .filter(field => field && typeof field === 'string')
    .join(' ')
    .toLowerCase();
}

/**
 * Format lastModified timestamp to human-readable date
 * @param {string} timestamp - ISO timestamp string
 * @returns {string} Formatted date string (e.g., "Jan 15, 2024")
 */
export function formatLastModified(timestamp) {
  if (!timestamp) return 'Unknown';
  
  try {
    const date = new Date(timestamp);
    
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }
    
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  } catch (error) {
    return 'Invalid Date';
  }
}

/**
 * Format lastModified timestamp to relative time (e.g., "2 days ago")
 * @param {string} timestamp - ISO timestamp string
 * @returns {string} Relative time string
 */
export function formatRelativeTime(timestamp) {
  if (!timestamp) return 'Unknown';
  
  try {
    const date = new Date(timestamp);
    const now = new Date();
    
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }
    
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    
    if (diffDays > 30) {
      return formatLastModified(timestamp);
    } else if (diffDays > 0) {
      return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
    } else if (diffHours > 0) {
      return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`;
    } else if (diffMinutes > 0) {
      return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
    } else {
      return 'Just now';
    }
  } catch (error) {
    return 'Invalid Date';
  }
}

/**
 * Get size range category for filtering
 * @param {number} bytes - File size in bytes
 * @returns {string} Size range category
 */
export function getSizeRange(bytes) {
  if (!bytes || bytes === 0) return 'Unknown';
  
  const gb = bytes / (1024 * 1024 * 1024);
  
  if (gb < 1) return '<1GB';
  if (gb < 4) return '1-4GB';
  if (gb < 8) return '4-8GB';
  if (gb < 16) return '8-16GB';
  return '>16GB';
}