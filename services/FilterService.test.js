import { describe, it, expect, beforeEach } from 'vitest';
import { FilterService } from './FilterService.js';

describe('FilterService', () => {
  let filterService;
  let mockModels;

  beforeEach(() => {
    filterService = new FilterService();
    
    // Create mock models for testing
    mockModels = [
      {
        id: '1',
        name: 'Mistral 7B Q4_K_M',
        modelId: 'mistralai/Mistral-7B-Instruct-v0.2',
        filename: 'mistral-7b-instruct-v0.2.Q4_K_M.gguf',
        url: 'https://example.com/model1.gguf',
        sizeBytes: 4 * 1024 * 1024 * 1024, // 4GB
        sizeFormatted: '4.0 GB',
        quantization: 'Q4_K_M',
        architecture: 'Mistral',
        family: 'mistralai',
        downloads: 1500,
        lastModified: '2024-01-01',
        tags: ['🔥 Popular', '🧠 7B'],
        searchText: 'mistralai/mistral-7b-instruct-v0.2 mistral-7b-instruct-v0.2.q4_k_m.gguf mistral mistralai q4_k_m'
      },
      {
        id: '2',
        name: 'LLaMA 13B Q8_0',
        modelId: 'meta-llama/Llama-2-13b-chat-hf',
        filename: 'llama-2-13b-chat.Q8_0.gguf',
        url: 'https://example.com/model2.gguf',
        sizeBytes: 14 * 1024 * 1024 * 1024, // 14GB
        sizeFormatted: '14.0 GB',
        quantization: 'Q8_0',
        architecture: 'Llama',
        family: 'meta-llama',
        downloads: 800,
        lastModified: '2024-01-02',
        tags: ['🧠 13B'],
        searchText: 'meta-llama/llama-2-13b-chat-hf llama-2-13b-chat.q8_0.gguf llama meta-llama q8_0'
      },
      {
        id: '3',
        name: 'Qwen 1.8B Q4_0',
        modelId: 'Qwen/Qwen1.5-1.8B-Chat',
        filename: 'qwen1.5-1.8b-chat.Q4_0.gguf',
        url: 'https://example.com/model3.gguf',
        sizeBytes: 1.2 * 1024 * 1024 * 1024, // 1.2GB
        sizeFormatted: '1.2 GB',
        quantization: 'Q4_0',
        architecture: 'Qwen',
        family: 'Qwen',
        downloads: 500,
        lastModified: '2024-01-03',
        tags: ['🧠 1-3B'],
        searchText: 'qwen/qwen1.5-1.8b-chat qwen1.5-1.8b-chat.q4_0.gguf qwen qwen q4_0'
      }
    ];
  });

  describe('applyFilters', () => {
    it('should return all models when no filters are applied', () => {
      const filterState = {
        quantizations: [],
        architectures: [],
        families: [],
        sizeRanges: [],
        searchQuery: ''
      };

      const result = filterService.applyFilters(mockModels, filterState);
      expect(result).toHaveLength(3);
      expect(result).toEqual(mockModels);
    });

    it('should filter by quantization type', () => {
      const filterState = {
        quantizations: ['Q4_K_M'],
        architectures: [],
        families: [],
        sizeRanges: [],
        searchQuery: ''
      };

      const result = filterService.applyFilters(mockModels, filterState);
      expect(result).toHaveLength(1);
      expect(result[0].quantization).toBe('Q4_K_M');
    });

    it('should filter by architecture', () => {
      const filterState = {
        quantizations: [],
        architectures: ['Mistral'],
        families: [],
        sizeRanges: [],
        searchQuery: ''
      };

      const result = filterService.applyFilters(mockModels, filterState);
      expect(result).toHaveLength(1);
      expect(result[0].architecture).toBe('Mistral');
    });

    it('should filter by family', () => {
      const filterState = {
        quantizations: [],
        architectures: [],
        families: ['Qwen'],
        sizeRanges: [],
        searchQuery: ''
      };

      const result = filterService.applyFilters(mockModels, filterState);
      expect(result).toHaveLength(1);
      expect(result[0].family).toBe('Qwen');
    });

    it('should filter by size range', () => {
      const filterState = {
        quantizations: [],
        architectures: [],
        families: [],
        sizeRanges: ['1-4GB'],
        searchQuery: ''
      };

      const result = filterService.applyFilters(mockModels, filterState);
      expect(result).toHaveLength(2); // Both Mistral (4GB) and Qwen (1.2GB) should match 1-4GB range
      expect(result.some(model => model.sizeBytes === 4 * 1024 * 1024 * 1024)).toBe(true);
    });

    it('should filter by search query', () => {
      const filterState = {
        quantizations: [],
        architectures: [],
        families: [],
        sizeRanges: [],
        searchQuery: 'mistral'
      };

      const result = filterService.applyFilters(mockModels, filterState);
      expect(result).toHaveLength(1);
      expect(result[0].architecture).toBe('Mistral');
    });

    it('should apply multiple filters simultaneously', () => {
      const filterState = {
        quantizations: ['Q4_K_M', 'Q4_0'],
        architectures: [],
        families: [],
        sizeRanges: [],
        searchQuery: ''
      };

      const result = filterService.applyFilters(mockModels, filterState);
      expect(result).toHaveLength(2);
      expect(result.every(model => ['Q4_K_M', 'Q4_0'].includes(model.quantization))).toBe(true);
    });

    it('should handle empty models array', () => {
      const filterState = {
        quantizations: [],
        architectures: [],
        families: [],
        sizeRanges: [],
        searchQuery: ''
      };

      const result = filterService.applyFilters([], filterState);
      expect(result).toHaveLength(0);
    });

    it('should handle invalid models array', () => {
      const filterState = {
        quantizations: [],
        architectures: [],
        families: [],
        sizeRanges: [],
        searchQuery: ''
      };

      const result = filterService.applyFilters(null, filterState);
      expect(result).toHaveLength(0);
    });
  });

  describe('matchesSizeRange', () => {
    it('should correctly match <1GB range', () => {
      const sizeBytes = 0.5 * 1024 * 1024 * 1024; // 0.5GB
      expect(filterService.matchesSizeRange(sizeBytes, ['<1GB'])).toBe(true);
      expect(filterService.matchesSizeRange(sizeBytes, ['1-4GB'])).toBe(false);
    });

    it('should correctly match 1-4GB range', () => {
      const sizeBytes = 2 * 1024 * 1024 * 1024; // 2GB
      expect(filterService.matchesSizeRange(sizeBytes, ['1-4GB'])).toBe(true);
      expect(filterService.matchesSizeRange(sizeBytes, ['<1GB'])).toBe(false);
    });

    it('should correctly match 4-8GB range', () => {
      const sizeBytes = 6 * 1024 * 1024 * 1024; // 6GB
      expect(filterService.matchesSizeRange(sizeBytes, ['4-8GB'])).toBe(true);
      expect(filterService.matchesSizeRange(sizeBytes, ['1-4GB'])).toBe(false);
    });

    it('should correctly match 8-16GB range', () => {
      const sizeBytes = 12 * 1024 * 1024 * 1024; // 12GB
      expect(filterService.matchesSizeRange(sizeBytes, ['8-16GB'])).toBe(true);
      expect(filterService.matchesSizeRange(sizeBytes, ['4-8GB'])).toBe(false);
    });

    it('should correctly match >32GB range', () => {
      const sizeBytes = 40 * 1024 * 1024 * 1024; // 40GB
      expect(filterService.matchesSizeRange(sizeBytes, ['>32GB'])).toBe(true);
      expect(filterService.matchesSizeRange(sizeBytes, ['16-32GB'])).toBe(false);
    });

    it('should match multiple ranges', () => {
      const sizeBytes = 2 * 1024 * 1024 * 1024; // 2GB
      expect(filterService.matchesSizeRange(sizeBytes, ['<1GB', '1-4GB'])).toBe(true);
    });
  });

  describe('getAvailableOptions', () => {
    it('should extract unique quantization types', () => {
      const options = filterService.getAvailableOptions(mockModels);
      expect(options.quantizations).toEqual(['Q4_0', 'Q4_K_M', 'Q8_0']);
    });

    it('should extract unique architectures', () => {
      const options = filterService.getAvailableOptions(mockModels);
      expect(options.architectures).toEqual(['Llama', 'Mistral', 'Qwen']);
    });

    it('should extract unique families', () => {
      const options = filterService.getAvailableOptions(mockModels);
      expect(options.families).toEqual(['Qwen', 'meta-llama', 'mistralai']);
    });

    it('should calculate size range counts', () => {
      const options = filterService.getAvailableOptions(mockModels);
      expect(options.sizeRanges).toHaveLength(2);
      
      const sizeRangeMap = options.sizeRanges.reduce((acc, item) => {
        acc[item.range] = item.count;
        return acc;
      }, {});
      
      expect(sizeRangeMap['1-4GB']).toBe(2); // Mistral (4GB) and Qwen (1.2GB)
      expect(sizeRangeMap['8-16GB']).toBe(1); // LLaMA (14GB)
    });

    it('should handle empty models array', () => {
      const options = filterService.getAvailableOptions([]);
      expect(options.quantizations).toHaveLength(0);
      expect(options.architectures).toHaveLength(0);
      expect(options.families).toHaveLength(0);
      expect(options.sizeRanges).toHaveLength(0);
    });

    it('should handle invalid models array', () => {
      const options = filterService.getAvailableOptions(null);
      expect(options.quantizations).toHaveLength(0);
      expect(options.architectures).toHaveLength(0);
      expect(options.families).toHaveLength(0);
      expect(options.sizeRanges).toHaveLength(0);
    });

    it('should filter out Unknown values', () => {
      const modelsWithUnknown = [
        ...mockModels,
        {
          id: '4',
          quantization: 'Unknown',
          architecture: 'Unknown',
          family: 'Unknown',
          sizeBytes: 1024 * 1024 * 1024,
          searchText: 'test'
        }
      ];

      const options = filterService.getAvailableOptions(modelsWithUnknown);
      expect(options.quantizations).not.toContain('Unknown');
      expect(options.architectures).not.toContain('Unknown');
      expect(options.families).not.toContain('Unknown');
    });
  });

  describe('performTextSearch', () => {
    it('should return all models when search query is empty', () => {
      const result = filterService.performTextSearch(mockModels, '');
      expect(result).toHaveLength(3);
    });

    it('should return all models when search query is null', () => {
      const result = filterService.performTextSearch(mockModels, null);
      expect(result).toHaveLength(3);
    });

    it('should search by single term', () => {
      const result = filterService.performTextSearch(mockModels, 'mistral');
      expect(result).toHaveLength(1);
      expect(result[0].architecture).toBe('Mistral');
    });

    it('should search by multiple terms', () => {
      const result = filterService.performTextSearch(mockModels, 'mistral q4_k_m');
      expect(result).toHaveLength(1);
      expect(result[0].quantization).toBe('Q4_K_M');
    });

    it('should be case insensitive', () => {
      const result = filterService.performTextSearch(mockModels, 'MISTRAL');
      expect(result).toHaveLength(1);
      expect(result[0].architecture).toBe('Mistral');
    });

    it('should handle partial matches', () => {
      const result = filterService.performTextSearch(mockModels, 'mistr');
      expect(result).toHaveLength(1);
      expect(result[0].architecture).toBe('Mistral');
    });
  });

  describe('getSuggestedSearchTerms', () => {
    it('should return suggestions based on partial query', () => {
      const suggestions = filterService.getSuggestedSearchTerms(mockModels, 'mi');
      expect(suggestions).toContain('Mistral');
      expect(suggestions).toContain('mistralai');
    });

    it('should return empty array for empty models', () => {
      const suggestions = filterService.getSuggestedSearchTerms([], 'test');
      expect(suggestions).toHaveLength(0);
    });

    it('should limit suggestions to 10 items', () => {
      const suggestions = filterService.getSuggestedSearchTerms(mockModels, '');
      expect(suggestions.length).toBeLessThanOrEqual(10);
    });
  });

  describe('validateFilterState', () => {
    it('should validate correct filter state', () => {
      const filterState = {
        quantizations: ['Q4_K_M'],
        architectures: ['Mistral'],
        families: ['mistralai'],
        sizeRanges: ['1-4GB'],
        searchQuery: 'test'
      };

      expect(filterService.validateFilterState(filterState)).toBe(true);
    });

    it('should reject null filter state', () => {
      expect(filterService.validateFilterState(null)).toBe(false);
    });

    it('should reject non-object filter state', () => {
      expect(filterService.validateFilterState('invalid')).toBe(false);
    });

    it('should reject filter state with non-array fields', () => {
      const filterState = {
        quantizations: 'not-an-array',
        architectures: [],
        families: [],
        sizeRanges: [],
        searchQuery: 'test'
      };

      expect(filterService.validateFilterState(filterState)).toBe(false);
    });

    it('should reject filter state with non-string searchQuery', () => {
      const filterState = {
        quantizations: [],
        architectures: [],
        families: [],
        sizeRanges: [],
        searchQuery: 123
      };

      expect(filterService.validateFilterState(filterState)).toBe(false);
    });
  });

  describe('clearCache', () => {
    it('should clear cached options', () => {
      // First call to cache options
      filterService.getAvailableOptions(mockModels);
      expect(filterService.availableOptions).not.toBeNull();

      // Clear cache
      filterService.clearCache();
      expect(filterService.availableOptions).toBeNull();
    });
  });
});