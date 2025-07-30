/**
 * Search and Filtering Functionality Tests
 * Requirements: 1.1, 1.2, 6.1
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { searchEngine } from '../services/SearchEngine.js';

describe('Search Engine', () => {
  const mockModels = [
    {
      modelId: 'microsoft/DialoGPT-medium',
      downloads: 1000,
      lastModified: '2024-01-01',
      files: [
        { filename: 'model.Q4_K_M.gguf' },
        { filename: 'model.Q8_0.gguf' }
      ]
    },
    {
      modelId: 'meta-llama/Llama-2-7b-chat-hf',
      downloads: 5000,
      lastModified: '2024-02-01',
      files: [
        { filename: 'model.Q4_K_M.gguf' },
        { filename: 'model.F16.gguf' }
      ]
    },
    {
      modelId: 'mistralai/Mistral-7B-v0.1',
      downloads: 3000,
      lastModified: '2024-01-15',
      files: [
        { filename: 'model.Q4_K_M.gguf' }
      ]
    }
  ];

  beforeEach(() => {
    searchEngine.indexModels(mockModels);
  });

  describe('Model Indexing', () => {
    it('should index models correctly', () => {
      expect(searchEngine.models).toHaveLength(3);
      expect(searchEngine.searchIndex).toBeDefined();
    });

    it('should handle empty model array', () => {
      searchEngine.indexModels([]);
      expect(searchEngine.models).toHaveLength(0);
    });

    it('should handle invalid model data', () => {
      const invalidModels = [
        { modelId: null },
        { downloads: 'invalid' },
        null,
        undefined
      ];
      
      expect(() => {
        searchEngine.indexModels(invalidModels);
      }).not.toThrow();
    });
  });

  describe('Search Functionality', () => {
    it('should return all models for empty query', () => {
      const results = searchEngine.search('');
      expect(results).toHaveLength(3);
    });

    it('should search by model name', () => {
      const results = searchEngine.search('llama');
      expect(results).toHaveLength(1);
      expect(results[0].model.modelId).toContain('Llama');
    });

    it('should search by organization', () => {
      const results = searchEngine.search('microsoft');
      expect(results).toHaveLength(1);
      expect(results[0].model.modelId).toContain('microsoft');
    });

    it('should search case-insensitively', () => {
      const results1 = searchEngine.search('LLAMA');
      const results2 = searchEngine.search('llama');
      expect(results1).toHaveLength(results2.length);
    });

    it('should handle partial matches', () => {
      const results = searchEngine.search('dial');
      expect(results).toHaveLength(1);
      expect(results[0].model.modelId).toContain('DialoGPT');
    });

    it('should return results with scores', () => {
      const results = searchEngine.search('llama');
      expect(results[0]).toHaveProperty('score');
      expect(results[0].score).toBeGreaterThan(0);
    });

    it('should sort results by relevance', () => {
      const results = searchEngine.search('model');
      if (results.length > 1) {
        expect(results[0].score).toBeGreaterThanOrEqual(results[1].score);
      }
    });

    it('should handle special characters in search', () => {
      const results = searchEngine.search('7b-chat');
      expect(results).toHaveLength(1);
    });

    it('should limit results when specified', () => {
      const results = searchEngine.search('', 2);
      expect(results).toHaveLength(2);
    });
  });

  describe('Search Performance', () => {
    it('should complete search within reasonable time', () => {
      const startTime = performance.now();
      searchEngine.search('test query');
      const endTime = performance.now();
      
      expect(endTime - startTime).toBeLessThan(100); // Less than 100ms
    });

    it('should handle large datasets efficiently', () => {
      const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
        modelId: `test/model-${i}`,
        downloads: Math.floor(Math.random() * 10000),
        lastModified: '2024-01-01',
        files: [{ filename: `model-${i}.gguf` }]
      }));

      const startTime = performance.now();
      searchEngine.indexModels(largeDataset);
      const indexTime = performance.now() - startTime;

      const searchStartTime = performance.now();
      searchEngine.search('model');
      const searchTime = performance.now() - searchStartTime;

      expect(indexTime).toBeLessThan(1000); // Less than 1 second
      expect(searchTime).toBeLessThan(200); // Less than 200ms
    });
  });

  describe('Error Handling', () => {
    it('should handle null search query', () => {
      expect(() => {
        searchEngine.search(null);
      }).not.toThrow();
    });

    it('should handle undefined search query', () => {
      expect(() => {
        searchEngine.search(undefined);
      }).not.toThrow();
    });

    it('should handle very long search queries', () => {
      const longQuery = 'a'.repeat(1000);
      expect(() => {
        searchEngine.search(longQuery);
      }).not.toThrow();
    });
  });
});

describe('Filtering Functionality', () => {
  // Mock ModelDiscoveryApp for testing filters
  class MockModelDiscoveryApp {
    constructor() {
      this.allModels = [
        {
          modelId: 'microsoft/DialoGPT-medium',
          downloads: 1000,
          files: [
            { filename: 'model.Q4_K_M.gguf' },
            { filename: 'model.Q8_0.gguf' }
          ]
        },
        {
          modelId: 'meta-llama/Llama-2-7b-chat-hf',
          downloads: 5000,
          files: [
            { filename: 'model.Q4_K_M.gguf' },
            { filename: 'model.F16.gguf' },
            { filename: 'model.Q2_K.gguf' }
          ]
        },
        {
          modelId: 'mistralai/Mistral-7B-v0.1',
          downloads: 3000,
          files: [
            { filename: 'model.Q4_K_M.gguf' }
          ]
        }
      ];
      this.activeFilters = {
        quantization: '',
        architecture: '',
        sizeRange: '',
        sortBy: 'name',
        sortOrder: 'asc'
      };
    }

    extractQuantization(filename) {
      const match = filename.match(/\.(Q\d+_K_[MS]|Q\d+_\d+|F\d+|BF\d+)\.gguf$/i);
      return match ? match[1] : null;
    }

    extractArchitecture(modelId) {
      const parts = modelId.toLowerCase();
      if (parts.includes('llama')) return 'Llama';
      if (parts.includes('mistral')) return 'Mistral';
      if (parts.includes('dialogpt')) return 'DialoGPT';
      return 'Other';
    }

    applyAdditionalFilters(models) {
      return models.filter(model => {
        // Quantization filter
        if (this.activeFilters.quantization) {
          const hasQuantization = model.files && model.files.some(file =>
            this.extractQuantization(file.filename) === this.activeFilters.quantization
          );
          if (!hasQuantization) return false;
        }

        // Architecture filter
        if (this.activeFilters.architecture) {
          const modelArchitecture = this.extractArchitecture(model.modelId);
          if (modelArchitecture !== this.activeFilters.architecture) return false;
        }

        // Size range filter
        if (this.activeFilters.sizeRange) {
          const fileCount = model.files ? model.files.length : 0;
          let matchesSize = false;
          
          switch (this.activeFilters.sizeRange) {
            case 'small':
              matchesSize = fileCount <= 2;
              break;
            case 'medium':
              matchesSize = fileCount > 2 && fileCount <= 4;
              break;
            case 'large':
              matchesSize = fileCount > 4;
              break;
            default:
              matchesSize = true;
          }
          
          if (!matchesSize) return false;
        }

        return true;
      });
    }
  }

  let app;

  beforeEach(() => {
    app = new MockModelDiscoveryApp();
  });

  describe('Quantization Filtering', () => {
    it('should filter by Q4_K_M quantization', () => {
      app.activeFilters.quantization = 'Q4_K_M';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(3); // All models have Q4_K_M
    });

    it('should filter by Q8_0 quantization', () => {
      app.activeFilters.quantization = 'Q8_0';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(1); // Only DialoGPT has Q8_0
    });

    it('should filter by F16 quantization', () => {
      app.activeFilters.quantization = 'F16';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(1); // Only Llama has F16
    });

    it('should return empty for non-existent quantization', () => {
      app.activeFilters.quantization = 'Q1_0';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(0);
    });
  });

  describe('Architecture Filtering', () => {
    it('should filter by Llama architecture', () => {
      app.activeFilters.architecture = 'Llama';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(1);
      expect(filtered[0].modelId).toContain('Llama');
    });

    it('should filter by Mistral architecture', () => {
      app.activeFilters.architecture = 'Mistral';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(1);
      expect(filtered[0].modelId).toContain('Mistral');
    });

    it('should filter by DialoGPT architecture', () => {
      app.activeFilters.architecture = 'DialoGPT';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(1);
      expect(filtered[0].modelId).toContain('DialoGPT');
    });
  });

  describe('Size Range Filtering', () => {
    it('should filter small models (≤2 files)', () => {
      app.activeFilters.sizeRange = 'small';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(2); // DialoGPT and Mistral
    });

    it('should filter medium models (3-4 files)', () => {
      app.activeFilters.sizeRange = 'medium';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(1); // Llama has 3 files
    });

    it('should filter large models (>4 files)', () => {
      app.activeFilters.sizeRange = 'large';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(0); // No models have >4 files
    });
  });

  describe('Combined Filtering', () => {
    it('should apply multiple filters correctly', () => {
      app.activeFilters.architecture = 'Llama';
      app.activeFilters.quantization = 'Q4_K_M';
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(1);
      expect(filtered[0].modelId).toContain('Llama');
    });

    it('should return empty when filters conflict', () => {
      app.activeFilters.architecture = 'Llama';
      app.activeFilters.quantization = 'Q8_0'; // Llama doesn't have Q8_0
      const filtered = app.applyAdditionalFilters(app.allModels);
      expect(filtered).toHaveLength(0);
    });
  });

  describe('Filter Performance', () => {
    it('should filter large datasets efficiently', () => {
      const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
        modelId: `test/model-${i}`,
        downloads: Math.floor(Math.random() * 10000),
        files: [{ filename: `model-${i}.Q4_K_M.gguf` }]
      }));

      app.allModels = largeDataset;
      app.activeFilters.quantization = 'Q4_K_M';

      const startTime = performance.now();
      const filtered = app.applyAdditionalFilters(app.allModels);
      const endTime = performance.now();

      expect(endTime - startTime).toBeLessThan(100); // Less than 100ms
      expect(filtered).toHaveLength(1000);
    });
  });
});