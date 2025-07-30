/**
 * SearchEngine Tests
 * 
 * Test suite for the SearchEngine class functionality
 * Task 4.1: Create real-time search functionality
 * Requirements: 1.2, 6.1, 6.2
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { SearchEngine } from './SearchEngine.js';

describe('SearchEngine', () => {
  let searchEngine;
  let testModels;

  beforeEach(() => {
    searchEngine = new SearchEngine();
    testModels = [
      {
        modelId: "microsoft/DialoGPT-medium",
        files: [
          { filename: "DialoGPT-medium.Q4_K_M.gguf" },
          { filename: "DialoGPT-medium.Q8_0.gguf" }
        ],
        downloads: 15420,
        lastModified: "2024-01-15T10:30:00Z"
      },
      {
        modelId: "meta-llama/Llama-2-7b-chat-hf",
        files: [
          { filename: "Llama-2-7b-chat.Q4_K_M.gguf" },
          { filename: "Llama-2-7b-chat.Q8_0.gguf" },
          { filename: "Llama-2-7b-chat.F16.gguf" }
        ],
        downloads: 89234,
        lastModified: "2024-01-20T14:45:00Z"
      },
      {
        modelId: "mistralai/Mistral-7B-Instruct-v0.1",
        files: [
          { filename: "Mistral-7B-Instruct-v0.1.Q4_K_M.gguf" },
          { filename: "Mistral-7B-Instruct-v0.1.Q6_K.gguf" }
        ],
        downloads: 67891,
        lastModified: "2024-01-18T09:15:00Z"
      }
    ];
  });

  describe('indexModels', () => {
    it('should index models correctly', () => {
      searchEngine.indexModels(testModels);
      
      expect(searchEngine.isIndexed).toBe(true);
      expect(searchEngine.models).toHaveLength(3);
      expect(searchEngine.searchIndex.size).toBe(3);
    });

    it('should create searchable text for models', () => {
      const searchableText = searchEngine.createSearchableText(testModels[0]);
      
      expect(searchableText).toContain('microsoft/DialoGPT-medium');
      expect(searchableText).toContain('DialoGPT-medium.Q4_K_M.gguf');
      expect(searchableText).toContain('Q4_K_M');
      expect(searchableText).toContain('DialoGPT');
    });

    it('should tokenize text correctly', () => {
      const tokens = searchEngine.tokenizeText('microsoft/DialoGPT-medium Q4_K_M');
      
      expect(tokens.has('microsoft')).toBe(true);
      expect(tokens.has('dialogpt')).toBe(true);
      expect(tokens.has('medium')).toBe(true);
      expect(tokens.has('q4_k_m')).toBe(true);
    });
  });

  describe('search', () => {
    beforeEach(() => {
      searchEngine.indexModels(testModels);
    });

    it('should return all models for empty query', () => {
      const results = searchEngine.search('');
      
      expect(results).toHaveLength(3);
      expect(results[0].score).toBe(1.0);
    });

    it('should find exact model matches', () => {
      const results = searchEngine.search('DialoGPT');
      
      expect(results.length).toBeGreaterThan(0);
      expect(results[0].model.modelId).toContain('DialoGPT');
      expect(results[0].score).toBeGreaterThan(1);
    });

    it('should find models by organization', () => {
      const results = searchEngine.search('microsoft');
      
      expect(results.length).toBeGreaterThan(0);
      expect(results[0].model.modelId).toContain('microsoft');
    });

    it('should find models by architecture', () => {
      const results = searchEngine.search('Llama');
      
      expect(results.length).toBeGreaterThan(0);
      expect(results[0].model.modelId).toContain('Llama');
    });

    it('should find models by quantization', () => {
      const results = searchEngine.search('Q4_K_M');
      
      expect(results.length).toBeGreaterThan(0);
      // All test models have Q4_K_M files
      expect(results).toHaveLength(3);
    });

    it('should rank results by relevance', () => {
      const results = searchEngine.search('microsoft');
      
      expect(results).toHaveLength(1);
      expect(results[0].model.modelId).toBe('microsoft/DialoGPT-medium');
      expect(results[0].score).toBeGreaterThan(1);
    });

    it('should handle partial matches', () => {
      const results = searchEngine.search('Dial');
      
      expect(results.length).toBeGreaterThan(0);
      expect(results[0].model.modelId).toContain('DialoGPT');
    });

    it('should be case insensitive', () => {
      const results1 = searchEngine.search('MICROSOFT');
      const results2 = searchEngine.search('microsoft');
      
      expect(results1).toHaveLength(results2.length);
      expect(results1[0].model.modelId).toBe(results2[0].model.modelId);
    });
  });

  describe('utility methods', () => {
    it('should extract architecture correctly', () => {
      expect(searchEngine.extractArchitecture('meta-llama/Llama-2-7b')).toBe('Llama');
      expect(searchEngine.extractArchitecture('mistralai/Mistral-7B')).toBe('Mistral');
      expect(searchEngine.extractArchitecture('microsoft/DialoGPT')).toBe('DialoGPT');
      expect(searchEngine.extractArchitecture('unknown/model')).toBe('Other');
    });

    it('should extract quantization correctly', () => {
      expect(searchEngine.extractQuantization('model.Q4_K_M.gguf')).toBe('Q4_K_M');
      expect(searchEngine.extractQuantization('model.Q8_0.gguf')).toBe('Q8_0');
      expect(searchEngine.extractQuantization('model.F16.gguf')).toBe('F16');
      expect(searchEngine.extractQuantization('model.gguf')).toBeNull();
    });

    it('should extract organization correctly', () => {
      expect(searchEngine.extractOrganization('microsoft/DialoGPT')).toBe('microsoft');
      expect(searchEngine.extractOrganization('meta-llama/Llama-2-7b')).toBe('meta-llama');
      expect(searchEngine.extractOrganization('standalone-model')).toBe('');
    });

    it('should extract model name correctly', () => {
      expect(searchEngine.extractModelName('microsoft/DialoGPT')).toBe('DialoGPT');
      expect(searchEngine.extractModelName('meta-llama/Llama-2-7b')).toBe('Llama-2-7b');
      expect(searchEngine.extractModelName('standalone-model')).toBe('standalone-model');
    });
  });

  describe('performance tracking', () => {
    beforeEach(() => {
      searchEngine.indexModels(testModels);
    });

    it('should track search statistics', () => {
      searchEngine.search('test');
      const stats = searchEngine.getSearchStats();
      
      expect(stats.totalSearches).toBe(1);
      expect(stats.lastSearchTime).toBeGreaterThan(0);
      expect(stats.isIndexed).toBe(true);
      expect(stats.modelCount).toBe(3);
    });

    it('should update average search time', () => {
      searchEngine.search('test1');
      searchEngine.search('test2');
      const stats = searchEngine.getSearchStats();
      
      expect(stats.totalSearches).toBe(2);
      expect(stats.averageSearchTime).toBeGreaterThan(0);
    });
  });

  describe('configuration', () => {
    it('should allow configuration updates', () => {
      const newConfig = { maxResults: 50, minQueryLength: 2 };
      searchEngine.updateConfig(newConfig);
      
      expect(searchEngine.config.maxResults).toBe(50);
      expect(searchEngine.config.minQueryLength).toBe(2);
    });

    it('should respect maxResults configuration', () => {
      searchEngine.updateConfig({ maxResults: 1 });
      searchEngine.indexModels(testModels);
      
      const results = searchEngine.search('Q4_K_M'); // Should match all 3 models
      expect(results).toHaveLength(1);
    });
  });

  describe('edge cases', () => {
    it('should handle empty model list', () => {
      searchEngine.indexModels([]);
      const results = searchEngine.search('test');
      
      expect(results).toHaveLength(0);
    });

    it('should handle models without files', () => {
      const modelsWithoutFiles = [
        { modelId: 'test/model', downloads: 100 }
      ];
      
      searchEngine.indexModels(modelsWithoutFiles);
      const results = searchEngine.search('test');
      
      expect(results).toHaveLength(1);
      expect(results[0].model.modelId).toBe('test/model');
    });

    it('should handle special characters in search', () => {
      searchEngine.indexModels(testModels);
      
      // Should not throw errors
      expect(() => searchEngine.search('test/model')).not.toThrow();
      expect(() => searchEngine.search('test-model')).not.toThrow();
      expect(() => searchEngine.search('test_model')).not.toThrow();
    });
  });
});