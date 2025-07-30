import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { ModelCard } from './ModelCard.js';

describe('ModelCard Component', () => {
  let modelCard;
  let container;
  let mockModel;

  beforeEach(() => {
    mockModel = {
      id: 'test-model-1',
      name: 'Test Model 7B Instruct',
      modelId: 'test/test-model-7b-instruct',
      filename: 'test-model-7b-instruct.Q4_K_M.gguf',
      url: 'https://example.com/download/test-model.gguf',
      sizeBytes: 4500000000,
      sizeFormatted: '4.2 GB',
      quantization: 'Q4_K_M',
      architecture: 'Mistral',
      family: 'TestFamily',
      downloads: 1234,
      lastModified: '2024-01-15T10:30:00Z',
      tags: ['🔥 Popular', '🧠 7B'],
      searchText: 'test model 7b instruct mistral q4_k_m'
    };

    modelCard = new ModelCard(mockModel);
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    modelCard.destroy();
    if (container.parentNode) {
      container.parentNode.removeChild(container);
    }
  });

  describe('render', () => {
    it('should create card element with correct structure', () => {
      const element = modelCard.render();
      
      expect(element.tagName).toBe('ARTICLE');
      expect(element.className).toContain('bg-white');
      expect(element.className).toContain('rounded-lg');
      expect(element.className).toContain('shadow-md');
    });

    it('should display model name', () => {
      const element = modelCard.render();
      const title = element.querySelector('h3');
      
      expect(title.textContent.trim()).toBe('Test Model 7B Instruct');
    });

    it('should display model ID', () => {
      const element = modelCard.render();
      const modelId = element.querySelector('p');
      
      expect(modelId.textContent.trim()).toBe('test/test-model-7b-instruct');
    });

    it('should display file size', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('4.2 GB');
    });

    it('should display quantization type', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('Q4_K_M');
    });

    it('should display architecture when available', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('Mistral');
    });

    it('should not display architecture when unknown', () => {
      const modelWithUnknownArch = { ...mockModel, architecture: 'Unknown' };
      const cardWithUnknownArch = new ModelCard(modelWithUnknownArch);
      const element = cardWithUnknownArch.render();
      const content = element.innerHTML;
      
      expect(content).not.toContain('Unknown');
      cardWithUnknownArch.destroy();
    });

    it('should display download count', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('1,234 downloads');
    });

    it('should display last modified date', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('Updated');
    });

    it('should have download button with correct link', () => {
      const element = modelCard.render();
      const downloadButton = element.querySelector('a[href="https://example.com/download/test-model.gguf"]');
      
      expect(downloadButton).toBeTruthy();
      expect(downloadButton.textContent.trim()).toContain('Download');
      expect(downloadButton.getAttribute('target')).toBe('_blank');
      expect(downloadButton.getAttribute('rel')).toBe('noopener noreferrer');
    });
  });

  describe('tags', () => {
    it('should display tags when available', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('🔥 Popular');
      expect(content).toContain('🧠 7B');
    });

    it('should handle model without tags', () => {
      const modelWithoutTags = { ...mockModel, tags: [] };
      const cardWithoutTags = new ModelCard(modelWithoutTags);
      const element = cardWithoutTags.render();
      
      // Should not crash and should not have tag elements
      expect(element).toBeTruthy();
      cardWithoutTags.destroy();
    });

    it('should apply correct styling for popular tags', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('bg-red-100');
      expect(content).toContain('text-red-800');
    });

    it('should apply correct styling for size tags', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('bg-purple-100');
      expect(content).toContain('text-purple-800');
    });
  });

  describe('description', () => {
    it('should display family when different from model name', () => {
      const element = modelCard.render();
      const content = element.innerHTML;
      
      expect(content).toContain('Family:');
      expect(content).toContain('TestFamily');
    });

    it('should not display family when unknown', () => {
      const modelWithUnknownFamily = { ...mockModel, family: 'Unknown' };
      const cardWithUnknownFamily = new ModelCard(modelWithUnknownFamily);
      const element = cardWithUnknownFamily.render();
      const content = element.innerHTML;
      
      expect(content).not.toContain('Family:');
      cardWithUnknownFamily.destroy();
    });
  });

  describe('updateModel', () => {
    it('should update model data', () => {
      const updatedModel = { ...mockModel, name: 'Updated Model Name' };
      modelCard.updateModel(updatedModel);
      
      expect(modelCard.getModel().name).toBe('Updated Model Name');
    });
  });

  describe('date formatting', () => {
    it('should format recent dates correctly', () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      
      const modelWithYesterday = { 
        ...mockModel, 
        lastModified: yesterday.toISOString() 
      };
      const cardWithYesterday = new ModelCard(modelWithYesterday);
      
      // Test the date formatting function directly
      const formattedDate = cardWithYesterday._formatDate(yesterday.toISOString());
      expect(formattedDate).toBe('yesterday');
      
      cardWithYesterday.destroy();
    });

    it('should handle invalid dates gracefully', () => {
      const modelWithInvalidDate = { 
        ...mockModel, 
        lastModified: 'invalid-date' 
      };
      const cardWithInvalidDate = new ModelCard(modelWithInvalidDate);
      
      // Test the date formatting function directly
      const formattedDate = cardWithInvalidDate._formatDate('invalid-date');
      expect(formattedDate).toBe('recently');
      
      cardWithInvalidDate.destroy();
    });
  });

  describe('HTML escaping', () => {
    it('should escape HTML in model name', () => {
      const modelWithHtml = { 
        ...mockModel, 
        name: '<script>alert("xss")</script>Test Model' 
      };
      const cardWithHtml = new ModelCard(modelWithHtml);
      const element = cardWithHtml.render();
      
      // Check that the text content is properly displayed (browser handles this)
      const title = element.querySelector('h3');
      expect(title.textContent).toContain('<script>alert("xss")</script>Test Model');
      
      // Test the escaping functions directly
      expect(cardWithHtml._escapeHtml('<script>test</script>')).toBe('&lt;script&gt;test&lt;/script&gt;');
      expect(cardWithHtml._escapeAttribute('<script>test</script>')).toBe('&lt;script&gt;test&lt;/script&gt;');
      
      cardWithHtml.destroy();
    });

    it('should have proper URL handling', () => {
      const modelWithUrl = { 
        ...mockModel, 
        url: 'https://example.com/file.gguf' 
      };
      const cardWithUrl = new ModelCard(modelWithUrl);
      const element = cardWithUrl.render();
      
      const downloadButton = element.querySelector('a');
      expect(downloadButton.getAttribute('href')).toBe('https://example.com/file.gguf');
      
      cardWithUrl.destroy();
    });
  });

  describe('destroy', () => {
    it('should remove element from DOM', () => {
      const element = modelCard.render();
      container.appendChild(element);
      
      expect(container.contains(element)).toBe(true);
      
      modelCard.destroy();
      
      expect(container.contains(element)).toBe(false);
    });

    it('should clean up references', () => {
      modelCard.render();
      modelCard.destroy();
      
      expect(modelCard.element).toBe(null);
      expect(modelCard.model).toBe(null);
    });
  });
});