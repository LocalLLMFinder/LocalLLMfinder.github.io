import { withErrorHandling, ErrorTypes, AppError } from '../utils/errorHandler.js';
import { withLoadingState, loadingStateManager } from '../utils/loadingStateManager.js';

/**
 * DataService handles fetching and processing of GGUF model data
 * Combines model metadata with size information and processes it for the UI
 */
export class DataService {
  constructor() {
    this.modelsCache = null;
    this.sizesCache = null;
    this.loadingManager = loadingStateManager;
  }

  /**
   * Load and process all model data
   * @returns {Promise<ProcessedModel[]>} Array of processed model objects
   */
  async loadModels() {
    return withLoadingState('load-models', async (updateProgress) => {
      return withErrorHandling(async () => {
        updateProgress(10, 'Fetching model data...');
        
        // Fetch both data sources concurrently
        const [modelsData, sizesData] = await Promise.all([
          this.fetchModelsData(),
          this.fetchSizesData()
        ]);

        updateProgress(70, 'Processing model data...');
        
        // Process and merge the data
        const processedModels = this.processRawData(modelsData, sizesData);
        
        updateProgress(100, 'Models loaded successfully');
        
        return processedModels;
      }, {
        retryable: true,
        context: { operation: 'loadModels' }
      });
    }, {
      loadingMessage: 'Loading model data...',
      successMessage: `Loaded ${this.modelsCache?.length || 0} models`
    });
  }

  /**
   * Fetch model metadata from gguf_models.json
   * @returns {Promise<Object[]>} Raw model data
   */
  async fetchModelsData() {
    if (this.modelsCache) {
      return this.modelsCache;
    }

    return withErrorHandling(async () => {
      const response = await fetch('./gguf_models.json');
      
      if (!response.ok) {
        throw new AppError(
          `Failed to fetch models data: ${response.status} ${response.statusText}`,
          ErrorTypes.NETWORK,
          response.status >= 500 ? 'HIGH' : 'MEDIUM',
          { url: './gguf_models.json', status: response.status }
        );
      }
      
      const data = await response.json();
      
      if (!Array.isArray(data)) {
        throw new AppError(
          'Invalid models data format: expected array',
          ErrorTypes.DATA_PARSING,
          'MEDIUM',
          { dataType: typeof data, url: './gguf_models.json' }
        );
      }

      this.modelsCache = data;
      return data;
    }, {
      retryable: true,
      context: { operation: 'fetchModelsData' }
    });
  }

  /**
   * Fetch size data from gguf_models_estimated_sizes.json
   * @returns {Promise<Object[]>} Raw size data
   */
  async fetchSizesData() {
    if (this.sizesCache) {
      return this.sizesCache;
    }

    return withErrorHandling(async () => {
      const response = await fetch('./gguf_models_estimated_sizes.json');
      
      if (!response.ok) {
        throw new AppError(
          `Failed to fetch sizes data: ${response.status} ${response.statusText}`,
          ErrorTypes.NETWORK,
          response.status >= 500 ? 'HIGH' : 'MEDIUM',
          { url: './gguf_models_estimated_sizes.json', status: response.status }
        );
      }
      
      const data = await response.json();
      
      if (!Array.isArray(data)) {
        throw new AppError(
          'Invalid sizes data format: expected array',
          ErrorTypes.DATA_PARSING,
          'MEDIUM',
          { dataType: typeof data, url: './gguf_models_estimated_sizes.json' }
        );
      }

      this.sizesCache = data;
      return data;
    }, {
      retryable: true,
      context: { operation: 'fetchSizesData' }
    });
  }

  /**
   * Process and merge raw data into ProcessedModel objects
   * @param {Object[]} modelsData - Raw model metadata
   * @param {Object[]} sizesData - Raw size data
   * @returns {ProcessedModel[]} Processed model objects
   */
  processRawData(modelsData, sizesData) {
    return withErrorHandling(() => {
      try {
        // Validate input data
        if (!Array.isArray(modelsData)) {
          throw new AppError(
            'Invalid models data: expected array',
            ErrorTypes.DATA_PARSING,
            'HIGH',
            { dataType: typeof modelsData }
          );
        }
        
        if (!Array.isArray(sizesData)) {
          throw new AppError(
            'Invalid sizes data: expected array',
            ErrorTypes.DATA_PARSING,
            'HIGH',
            { dataType: typeof sizesData }
          );
        }

        // Create a lookup map for sizes by model_id and filename
        const sizesMap = new Map();
        let sizesProcessed = 0;
        let sizesSkipped = 0;
        
        sizesData.forEach((sizeEntry, index) => {
          try {
            if (!sizeEntry.model_id || !sizeEntry.filename) {
              sizesSkipped++;
              console.warn(`Skipping size entry ${index}: missing model_id or filename`, sizeEntry);
              return;
            }
            
            const key = `${sizeEntry.model_id}:${sizeEntry.filename}`;
            sizesMap.set(key, sizeEntry);
            sizesProcessed++;
          } catch (error) {
            sizesSkipped++;
            console.warn(`Error processing size entry ${index}:`, error);
          }
        });

        console.log(`Processed ${sizesProcessed} size entries, skipped ${sizesSkipped}`);

        const processedModels = [];
        let modelsProcessed = 0;
        let modelsSkipped = 0;
        let filesProcessed = 0;
        let filesSkipped = 0;

        modelsData.forEach((model, modelIndex) => {
          try {
            if (!model.modelId || !Array.isArray(model.files)) {
              modelsSkipped++;
              console.warn(`Skipping invalid model entry ${modelIndex}:`, {
                hasModelId: !!model.modelId,
                filesType: typeof model.files,
                isFilesArray: Array.isArray(model.files)
              });
              return;
            }

            let modelFilesProcessed = 0;
            model.files.forEach((file, fileIndex) => {
              try {
                if (!file.filename) {
                  filesSkipped++;
                  console.warn(`Skipping file ${fileIndex} in model ${model.modelId}: no filename`);
                  return;
                }

                const processedModel = this.createProcessedModel(model, file, sizesMap);
                processedModels.push(processedModel);
                filesProcessed++;
                modelFilesProcessed++;
                
              } catch (error) {
                filesSkipped++;
                console.warn(`Failed to process file ${fileIndex} in model ${model.modelId}:`, error);
                
                // Create error context for debugging
                errorHandler.handleError(new AppError(
                  `Failed to process model file`,
                  ErrorTypes.DATA_PARSING,
                  'LOW',
                  {
                    modelId: model.modelId,
                    filename: file.filename,
                    fileIndex,
                    originalError: error.message
                  }
                ), { showToUser: false });
              }
            });

            if (modelFilesProcessed > 0) {
              modelsProcessed++;
            } else {
              modelsSkipped++;
            }

          } catch (error) {
            modelsSkipped++;
            console.warn(`Failed to process model ${modelIndex}:`, error);
            
            errorHandler.handleError(new AppError(
              `Failed to process model`,
              ErrorTypes.DATA_PARSING,
              'LOW',
              {
                modelIndex,
                modelId: model?.modelId,
                originalError: error.message
              }
            ), { showToUser: false });
          }
        });

        console.log(`Data processing complete: ${processedModels.length} models created from ${modelsProcessed} model entries (${modelsSkipped} skipped), ${filesProcessed} files processed (${filesSkipped} skipped)`);

        if (processedModels.length === 0) {
          throw new AppError(
            'No valid models could be processed from the data',
            ErrorTypes.DATA_PARSING,
            'HIGH',
            {
              totalModels: modelsData.length,
              totalSizes: sizesData.length,
              modelsSkipped,
              filesSkipped
            }
          );
        }

        return processedModels;
        
      } catch (error) {
        if (error instanceof AppError) {
          throw error;
        }
        
        console.error('Critical error in processRawData:', error);
        throw new AppError(
          'Failed to process model data',
          ErrorTypes.DATA_PARSING,
          'HIGH',
          { originalError: error.message, stack: error.stack }
        );
      }
    }, {
      retryable: false,
      context: { operation: 'processRawData' }
    });
  }

  /**
   * Create a ProcessedModel object from raw data
   * @param {Object} model - Raw model metadata
   * @param {Object} file - Raw file data
   * @param {Map} sizesMap - Size lookup map
   * @returns {ProcessedModel} Processed model object
   */
  createProcessedModel(model, file, sizesMap) {
    try {
      // Validate required fields
      if (!model.modelId) {
        throw new AppError(
          'Model missing required modelId',
          ErrorTypes.VALIDATION,
          'MEDIUM',
          { model }
        );
      }
      
      if (!file.filename) {
        throw new AppError(
          'File missing required filename',
          ErrorTypes.VALIDATION,
          'MEDIUM',
          { file, modelId: model.modelId }
        );
      }

      // Look up size information
      const sizeKey = `${model.modelId}:${file.filename}`;
      const sizeEntry = sizesMap.get(sizeKey);
      
      // Extract metadata from filename with error handling
      let metadata;
      try {
        metadata = this.extractMetadata(file.filename, model.modelId);
      } catch (error) {
        console.warn(`Failed to extract metadata for ${file.filename}:`, error);
        metadata = {
          quantization: 'Unknown',
          architecture: 'Unknown',
          family: 'Unknown'
        };
      }
      
      // Create unique ID
      const id = `${model.modelId}:${file.filename}`;
      
      // Determine size with validation
      let sizeBytes = 0;
      if (sizeEntry?.estimated_size_bytes) {
        if (typeof sizeEntry.estimated_size_bytes === 'number' && sizeEntry.estimated_size_bytes > 0) {
          sizeBytes = sizeEntry.estimated_size_bytes;
        } else {
          console.warn(`Invalid size data for ${sizeKey}:`, sizeEntry.estimated_size_bytes);
        }
      }
      
      // Generate download URL with fallback
      let url;
      try {
        url = sizeEntry?.url || `https://huggingface.co/${model.modelId}/resolve/main/${encodeURIComponent(file.filename)}`;
        
        // Validate URL format
        new URL(url);
      } catch (urlError) {
        console.warn(`Invalid URL for ${sizeKey}, using fallback:`, urlError);
        url = `https://huggingface.co/${model.modelId}/resolve/main/${encodeURIComponent(file.filename)}`;
      }
      
      // Generate tags with error handling
      let tags;
      try {
        tags = this.generateTags(model, metadata, sizeBytes);
      } catch (error) {
        console.warn(`Failed to generate tags for ${file.filename}:`, error);
        tags = [];
      }
      
      // Generate search text with error handling
      let searchText;
      try {
        searchText = this.generateSearchText(model, file, metadata);
      } catch (error) {
        console.warn(`Failed to generate search text for ${file.filename}:`, error);
        searchText = `${model.modelId} ${file.filename}`.toLowerCase();
      }
      
      const processedModel = {
        id,
        name: this.cleanModelName(file.filename),
        modelId: model.modelId,
        filename: file.filename,
        url,
        sizeBytes,
        sizeFormatted: this.formatFileSize(sizeBytes),
        quantization: metadata.quantization,
        architecture: metadata.architecture,
        family: metadata.family,
        downloads: typeof model.downloads === 'number' ? model.downloads : 0,
        lastModified: model.lastModified || '',
        tags,
        searchText
      };

      return processedModel;
      
    } catch (error) {
      if (error instanceof AppError) {
        throw error;
      }
      
      throw new AppError(
        `Failed to create processed model`,
        ErrorTypes.DATA_PARSING,
        'MEDIUM',
        {
          modelId: model?.modelId,
          filename: file?.filename,
          originalError: error.message
        }
      );
    }
  }

  /**
   * Extract metadata from filename and modelId
   * @param {string} filename - Model filename
   * @param {string} modelId - HuggingFace model ID
   * @returns {Object} Extracted metadata
   */
  extractMetadata(filename, modelId) {
    try {
      // Validate inputs
      if (typeof filename !== 'string' || !filename.trim()) {
        throw new AppError(
          'Invalid filename for metadata extraction',
          ErrorTypes.VALIDATION,
          'MEDIUM',
          { filename, modelId }
        );
      }
      
      if (typeof modelId !== 'string' || !modelId.trim()) {
        throw new AppError(
          'Invalid modelId for metadata extraction',
          ErrorTypes.VALIDATION,
          'MEDIUM',
          { filename, modelId }
        );
      }

      // Extract quantization type with error handling
      let quantization = 'Unknown';
      try {
        const quantMatch = filename.match(/\.(Q\d+_[KM]+|IQ\d+_[A-Z]+|f\d+|BF16)\.gguf$/i);
        quantization = quantMatch?.[1] || 'Unknown';
      } catch (error) {
        console.warn(`Failed to extract quantization from ${filename}:`, error);
      }

      // Extract architecture from filename or modelId with error handling
      let architecture = 'Unknown';
      try {
        const archPatterns = [
          /mistral/i, /llama/i, /qwen/i, /phi/i, /gemma/i, /codellama/i,
          /vicuna/i, /alpaca/i, /falcon/i, /mpt/i, /gpt/i, /claude/i
        ];
        
        const searchText = `${filename} ${modelId}`.toLowerCase();
        
        for (const pattern of archPatterns) {
          if (pattern.test(searchText)) {
            architecture = pattern.source.replace(/[\/\\^$*+?.()|[\]{}]/g, '').replace('i', '');
            architecture = architecture.charAt(0).toUpperCase() + architecture.slice(1);
            break;
          }
        }
      } catch (error) {
        console.warn(`Failed to extract architecture from ${filename}:`, error);
      }

      // Extract family from modelId with error handling
      let family = 'Unknown';
      try {
        const familyMatch = modelId.match(/^([^\/]+)\//);
        family = familyMatch?.[1] || 'Unknown';
      } catch (error) {
        console.warn(`Failed to extract family from ${modelId}:`, error);
      }

      return {
        quantization,
        architecture,
        family
      };
      
    } catch (error) {
      if (error instanceof AppError) {
        throw error;
      }
      
      console.warn(`Error extracting metadata from ${filename}:`, error);
      return {
        quantization: 'Unknown',
        architecture: 'Unknown',
        family: 'Unknown'
      };
    }
  }

  /**
   * Generate tags based on model properties
   * @param {Object} model - Raw model data
   * @param {Object} metadata - Extracted metadata
   * @param {number} sizeBytes - File size in bytes
   * @returns {string[]} Array of tags
   */
  generateTags(model, metadata, sizeBytes) {
    try {
      const tags = [];

      // Popular tag based on downloads with validation
      try {
        const downloads = typeof model.downloads === 'number' ? model.downloads : 0;
        if (downloads > 1000) {
          tags.push('🔥 Popular');
        }
      } catch (error) {
        console.warn('Error processing downloads for tags:', error);
      }

      // Size-based tags with validation
      try {
        if (typeof sizeBytes === 'number' && sizeBytes > 0) {
          const sizeGB = sizeBytes / (1024 * 1024 * 1024);
          if (sizeGB > 0) {
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
            } else {
              tags.push('🧠 70B+');
            }
          }
        }
      } catch (error) {
        console.warn('Error processing size for tags:', error);
      }

      return tags;
      
    } catch (error) {
      console.warn('Error generating tags:', error);
      return [];
    }
  }

  /**
   * Generate searchable text for a model
   * @param {Object} model - Raw model data
   * @param {Object} file - Raw file data
   * @param {Object} metadata - Extracted metadata
   * @returns {string} Combined searchable text
   */
  generateSearchText(model, file, metadata) {
    try {
      const searchParts = [];
      
      // Add model ID if valid
      if (model.modelId && typeof model.modelId === 'string') {
        searchParts.push(model.modelId);
      }
      
      // Add filename if valid
      if (file.filename && typeof file.filename === 'string') {
        searchParts.push(file.filename);
      }
      
      // Add metadata if valid
      if (metadata) {
        if (metadata.architecture && metadata.architecture !== 'Unknown') {
          searchParts.push(metadata.architecture);
        }
        if (metadata.family && metadata.family !== 'Unknown') {
          searchParts.push(metadata.family);
        }
        if (metadata.quantization && metadata.quantization !== 'Unknown') {
          searchParts.push(metadata.quantization);
        }
      }
      
      return searchParts.filter(Boolean).join(' ').toLowerCase();
      
    } catch (error) {
      console.warn('Error generating search text:', error);
      // Fallback to basic search text
      const fallback = `${model?.modelId || ''} ${file?.filename || ''}`.trim();
      return fallback.toLowerCase();
    }
  }

  /**
   * Clean model name for display
   * @param {string} filename - Original filename
   * @returns {string} Cleaned display name
   */
  cleanModelName(filename) {
    try {
      if (typeof filename !== 'string') {
        console.warn('Invalid filename for cleaning:', filename);
        return 'Unknown Model';
      }
      
      return filename
        .replace(/\.gguf$/, '')
        .replace(/[-_]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim() || 'Unknown Model';
        
    } catch (error) {
      console.warn('Error cleaning model name:', error);
      return 'Unknown Model';
    }
  }

  /**
   * Format file size to human-readable format
   * @param {number} bytes - Size in bytes
   * @returns {string} Formatted size string
   */
  formatFileSize(bytes) {
    try {
      if (typeof bytes !== 'number' || bytes < 0 || !isFinite(bytes)) {
        return 'Unknown';
      }
      
      if (bytes === 0) return 'Unknown';
      
      const units = ['B', 'KB', 'MB', 'GB', 'TB'];
      let size = bytes;
      let unitIndex = 0;
      
      while (size >= 1024 && unitIndex < units.length - 1) {
        size /= 1024;
        unitIndex++;
      }
      
      const formattedSize = size.toFixed(unitIndex > 0 ? 1 : 0);
      return `${formattedSize} ${units[unitIndex]}`;
      
    } catch (error) {
      console.warn('Error formatting file size:', error);
      return 'Unknown';
    }
  }

  /**
   * Clear cached data (useful for testing or forced refresh)
   */
  clearCache() {
    this.modelsCache = null;
    this.sizesCache = null;
  }
}