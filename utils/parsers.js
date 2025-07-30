/**
 * Utility functions for parsing GGUF model filenames and extracting metadata
 */

/**
 * Parse filename to extract quantization, architecture, and model size
 * @param {string} filename - GGUF model filename
 * @returns {Object} Parsed metadata
 */
export function parseFilename(filename) {
  if (!filename || typeof filename !== 'string') {
    return {
      quantization: 'Unknown',
      architecture: 'Unknown',
      modelSize: null,
      isValid: false
    };
  }

  // Extract quantization type (Q4_K_M, Q8_0, f32, BF16, etc.)
  const quantMatch = filename.match(/\.(Q\d+_[KM_0]+|IQ\d+_[A-Z]+|f\d+|BF16)\.gguf$/i);
  const quantization = quantMatch?.[1] || 'Unknown';

  // Extract model size (7B, 13B, 1.5B, etc.)
  const sizeMatch = filename.match(/(\d+\.?\d*)[BM]/i);
  const modelSize = sizeMatch?.[1] ? parseFloat(sizeMatch[1]) : null;

  // Extract architecture from filename
  const architecture = extractArchitectureFromText(filename);

  return {
    quantization,
    architecture,
    modelSize,
    isValid: filename.endsWith('.gguf')
  };
}

/**
 * Extract metadata from modelId and filename
 * @param {string} modelId - HuggingFace model ID (e.g., "microsoft/DialoGPT-medium")
 * @param {string} filename - Model filename
 * @returns {Object} Extracted metadata
 */
export function extractMetadata(modelId, filename = '') {
  if (!modelId || typeof modelId !== 'string') {
    return {
      family: 'Unknown',
      organization: 'Unknown',
      modelName: 'Unknown',
      architecture: 'Unknown',
      quantization: 'Unknown',
      modelSize: null
    };
  }

  // Parse filename for technical details
  const filenameData = parseFilename(filename);

  // Extract family/organization from modelId
  const parts = modelId.split('/');
  const organization = parts[0] || 'Unknown';
  const modelName = parts[1] || 'Unknown';

  // Use organization as family, but clean it up
  const family = cleanFamilyName(organization);

  // Try to extract architecture from both modelId and filename
  const combinedText = `${modelId} ${filename}`;
  const architecture = extractArchitectureFromText(combinedText) || filenameData.architecture;

  return {
    family,
    organization,
    modelName,
    architecture,
    quantization: filenameData.quantization,
    modelSize: filenameData.modelSize
  };
}

/**
 * Extract architecture from text (filename or modelId)
 * @param {string} text - Text to analyze
 * @returns {string} Detected architecture
 */
function extractArchitectureFromText(text) {
  if (!text) return 'Unknown';

  const lowerText = text.toLowerCase();
  
  // Architecture patterns in order of specificity
  const architecturePatterns = [
    { pattern: /codellama|code-llama/i, name: 'CodeLlama' },
    { pattern: /llama-?3/i, name: 'Llama3' },
    { pattern: /llama-?2/i, name: 'Llama2' },
    { pattern: /llama/i, name: 'Llama' },
    { pattern: /mistral/i, name: 'Mistral' },
    { pattern: /qwen/i, name: 'Qwen' },
    { pattern: /phi-?3/i, name: 'Phi3' },
    { pattern: /phi/i, name: 'Phi' },
    { pattern: /gemma/i, name: 'Gemma' },
    { pattern: /vicuna/i, name: 'Vicuna' },
    { pattern: /alpaca/i, name: 'Alpaca' },
    { pattern: /falcon/i, name: 'Falcon' },
    { pattern: /mpt/i, name: 'MPT' },
    { pattern: /gpt-?4/i, name: 'GPT4' },
    { pattern: /gpt-?3/i, name: 'GPT3' },
    { pattern: /gpt/i, name: 'GPT' },
    { pattern: /claude/i, name: 'Claude' },
    { pattern: /bloom/i, name: 'BLOOM' },
    { pattern: /opt/i, name: 'OPT' },
    { pattern: /t5/i, name: 'T5' },
    { pattern: /bert/i, name: 'BERT' },
    { pattern: /roberta/i, name: 'RoBERTa' },
    { pattern: /electra/i, name: 'ELECTRA' }
  ];

  for (const { pattern, name } of architecturePatterns) {
    if (pattern.test(lowerText)) {
      return name;
    }
  }

  return 'Unknown';
}

/**
 * Clean family name for display
 * @param {string} familyName - Raw family name
 * @returns {string} Cleaned family name
 */
function cleanFamilyName(familyName) {
  if (!familyName) return 'Unknown';
  
  // Only remove common suffixes, keep organization names
  const cleaned = familyName
    .replace(/-?(gguf|models?)$/i, '')
    .replace(/[-_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
    
  if (!cleaned) return 'Unknown';
  
  return cleaned
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Generate tags based on download count and model properties
 * @param {Object} model - Model data with downloads, etc.
 * @param {Object} metadata - Extracted metadata
 * @param {number} sizeBytes - File size in bytes
 * @returns {string[]} Array of tags
 */
export function generateTags(model, metadata, sizeBytes = 0) {
  const tags = [];

  // Popular tag based on downloads
  const downloads = model?.downloads || 0;
  if (downloads > 1000) {
    tags.push('🔥 Popular');
  } else if (downloads > 100) {
    tags.push('⭐ Trending');
  }

  // Size-based tags
  if (sizeBytes > 0) {
    const sizeGB = sizeBytes / (1024 * 1024 * 1024);
    
    if (sizeGB < 1) {
      tags.push('🧠 <1B');
    } else if (sizeGB < 4) {
      tags.push('🧠 1-3B');
    } else if (sizeGB < 8) {
      tags.push('🧠 7B');
    } else if (sizeGB < 16) {
      tags.push('🧠 13B');
    } else if (sizeGB < 35) {
      tags.push('🧠 30B');
    } else if (sizeGB < 80) {
      tags.push('🧠 70B');
    } else {
      tags.push('🧠 100B+');
    }
  }

  // Model size from filename if available
  if (metadata?.modelSize) {
    const size = metadata.modelSize;
    if (size < 1) {
      tags.push('🧠 <1B');
    } else if (size < 4) {
      tags.push(`🧠 ${size}B`);
    } else if (size < 10) {
      tags.push(`🧠 ${Math.round(size)}B`);
    } else {
      tags.push(`🧠 ${Math.round(size)}B`);
    }
  }

  // Architecture-specific tags
  if (metadata?.architecture && metadata.architecture !== 'Unknown') {
    tags.push(`🏗️ ${metadata.architecture}`);
  }

  // Quantization quality tags
  if (metadata?.quantization) {
    const quant = metadata.quantization.toLowerCase();
    if (quant.includes('f32') || quant.includes('f16')) {
      tags.push('💎 Full Precision');
    } else if (quant.includes('q8')) {
      tags.push('⚡ High Quality');
    } else if (quant.includes('q4')) {
      tags.push('🚀 Balanced');
    } else if (quant.includes('q2')) {
      tags.push('📦 Compact');
    }
  }

  // Remove duplicates and limit to reasonable number
  return [...new Set(tags)].slice(0, 4);
}

/**
 * Validate if a filename is a valid GGUF file
 * @param {string} filename - Filename to validate
 * @returns {boolean} True if valid GGUF filename
 */
export function isValidGGUFFilename(filename) {
  if (!filename || typeof filename !== 'string') {
    return false;
  }
  
  return filename.toLowerCase().endsWith('.gguf') && 
         filename.length > 5 && 
         !filename.includes('..') &&
         !/[<>:"|?*]/.test(filename);
}

/**
 * Extract model series/version from filename or modelId
 * @param {string} text - Text to analyze
 * @returns {string|null} Detected version/series
 */
export function extractModelVersion(text) {
  if (!text) return null;
  
  const versionPatterns = [
    /v(\d+\.?\d*)/i,
    /version[_-]?(\d+\.?\d*)/i,
    /(\d+\.?\d*)[_-]?instruct/i,
    /instruct[_-]?(\d+\.?\d*)/i
  ];
  
  for (const pattern of versionPatterns) {
    const match = text.match(pattern);
    if (match) {
      return match[1];
    }
  }
  
  return null;
}