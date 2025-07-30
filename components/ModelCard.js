/**
 * ModelCard Component - Responsive model card with lazy loading and accessibility
 * 
 * This component creates responsive model cards with download links, metadata,
 * lazy loading for performance, hover states, and accessibility features.
 * 
 * Task 4.3: Build responsive model card components
 * Requirements: 1.3, 1.4
 */

/**
 * ModelCard class for creating responsive model cards
 * Requirements: 1.3, 1.4
 */
export class ModelCard {
  constructor(model, options = {}) {
    this.model = model;
    this.options = {
      lazyLoad: typeof window !== 'undefined' && 'IntersectionObserver' in window,
      showSearchHighlight: false,
      searchQuery: '',
      searchResult: null,
      ...options
    };
    
    this.element = null;
    this.isVisible = false;
    this.observer = null;
  }

  /**
   * Create the model card element
   * @returns {HTMLElement} Model card element
   */
  createElement() {
    const card = document.createElement('article');
    card.className = 'model-card bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-all duration-200 relative group';
    card.setAttribute('role', 'article');
    card.setAttribute('aria-label', `Model: ${this.model.modelId}`);
    card.setAttribute('tabindex', '0');

    // Add data attributes for filtering and searching
    card.setAttribute('data-model-id', this.model.modelId);
    card.setAttribute('data-architecture', this.extractArchitecture(this.model.modelId));
    card.setAttribute('data-downloads', this.model.downloads || 0);

    if (this.options.lazyLoad) {
      card.classList.add('lazy-load');
      this.setupLazyLoading(card);
    } else {
      this.renderCardContent(card);
    }

    this.element = card;
    return card;
  }

  /**
   * Set up lazy loading for the card
   * @param {HTMLElement} card - Card element
   */
  setupLazyLoading(card) {
    // Create placeholder content
    card.innerHTML = this.createPlaceholderContent();

    // Set up intersection observer for lazy loading
    if ('IntersectionObserver' in window) {
      this.observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting && !this.isVisible) {
            this.isVisible = true;
            this.renderCardContent(card);
            this.observer.unobserve(card);
          }
        });
      }, {
        rootMargin: '50px 0px',
        threshold: 0.1
      });

      this.observer.observe(card);
    } else {
      // Fallback for browsers without IntersectionObserver
      this.renderCardContent(card);
    }
  }

  /**
   * Create placeholder content for lazy loading
   * @returns {string} Placeholder HTML
   */
  createPlaceholderContent() {
    return `
      <div class="animate-pulse">
        <div class="flex items-start justify-between mb-4">
          <div class="flex-1 min-w-0">
            <div class="h-6 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div class="h-4 bg-gray-200 rounded w-1/2"></div>
          </div>
          <div class="flex-shrink-0 ml-4">
            <div class="h-6 w-16 bg-gray-200 rounded-full"></div>
          </div>
        </div>
        <div class="mb-4">
          <div class="flex items-center space-x-4">
            <div class="h-4 bg-gray-200 rounded w-20"></div>
            <div class="h-4 bg-gray-200 rounded w-24"></div>
          </div>
        </div>
        <div class="mb-4">
          <div class="h-4 bg-gray-200 rounded w-24 mb-2"></div>
          <div class="space-y-1">
            <div class="h-8 bg-gray-200 rounded"></div>
            <div class="h-8 bg-gray-200 rounded"></div>
          </div>
        </div>
        <div class="flex items-center justify-between">
          <div class="h-4 bg-gray-200 rounded w-16"></div>
          <div class="h-10 w-24 bg-gray-200 rounded"></div>
        </div>
      </div>
    `;
  }

  /**
   * Render the actual card content
   * @param {HTMLElement} card - Card element
   */
  renderCardContent(card) {
    // Extract model information
    const [org, ...nameParts] = this.model.modelId.split('/');
    const modelName = nameParts.join('/') || org;
    const organization = nameParts.length > 0 ? org : '';

    // Apply search highlighting if enabled
    const highlightedModelName = this.options.showSearchHighlight ? 
      this.highlightSearchTerms(modelName, this.options.searchQuery) : modelName;
    const highlightedOrganization = this.options.showSearchHighlight ? 
      this.highlightSearchTerms(organization, this.options.searchQuery) : organization;

    // Format metadata
    const downloadCount = this.model.downloads ? this.formatNumber(this.model.downloads) : 'N/A';
    const lastModified = this.model.lastModified ? 
      new Date(this.model.lastModified).toLocaleDateString() : 'N/A';
    const architecture = this.extractArchitecture(this.model.modelId);

    // Create file list with better formatting
    const fileList = this.createFileList();

    // Add search score indicator if available
    const searchScoreIndicator = this.options.searchResult && this.options.searchResult.score > 1 ? 
      `<div class="absolute top-2 right-2 bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
        Match: ${Math.round(this.options.searchResult.score * 10) / 10}
      </div>` : '';

    card.innerHTML = `
      ${searchScoreIndicator}
      
      <!-- Header Section -->
      <div class="flex items-start justify-between mb-4">
        <div class="flex-1 min-w-0">
          <h3 class="text-lg font-semibold text-gray-900 truncate group-hover:text-blue-600 transition-colors">
            <a href="/model/${this.createModelSlug(this.model.modelId)}" 
               class="hover:text-blue-600 focus:text-blue-600 focus:outline-none focus:underline"
               title="View ${this.model.modelId} details">
              ${highlightedModelName}
            </a>
          </h3>
          ${organization ? `<p class="text-sm text-gray-600 truncate">
            <a href="/family/${organization.toLowerCase().replace(/[^a-z0-9]/g, '-')}" 
               class="hover:text-blue-600 focus:text-blue-600 focus:outline-none focus:underline"
               title="View all ${organization} models">
              ${highlightedOrganization}
            </a>
          </p>` : ''}
        </div>
        <div class="flex-shrink-0 ml-4">
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            ${this.options.showSearchHighlight ? this.highlightSearchTerms(architecture, this.options.searchQuery) : architecture}
          </span>
        </div>
      </div>

      <!-- Metadata Section -->
      <div class="mb-4">
        <div class="flex items-center text-sm text-gray-600 space-x-4 flex-wrap gap-y-1">
          <div class="flex items-center" title="Download count">
            <svg class="w-4 h-4 mr-1 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"></path>
            </svg>
            <span>${downloadCount} downloads</span>
          </div>
          <div class="flex items-center" title="Last modified date">
            <svg class="w-4 h-4 mr-1 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <span>${lastModified}</span>
          </div>
        </div>
      </div>

      <!-- Files Section -->
      <div class="mb-4">
        <h4 class="text-sm font-medium text-gray-900 mb-2 flex items-center">
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.29-1.009-5.824-2.562M15 6.306a7.962 7.962 0 00-6 0m6 0V5a2 2 0 00-2-2H9a2 2 0 00-2 2v1.306m6 0V7a2 2 0 012 2v4M9 6.306V7a2 2 0 00-2-2H7a2 2 0 00-2 2v4.01M15 6.306V7a2 2 0 012 2v4.01"></path>
          </svg>
          Available Files:
        </h4>
        <div class="space-y-1 max-h-32 overflow-y-auto custom-scrollbar">
          ${fileList}
        </div>
      </div>

      <!-- Footer Section -->
      <div class="flex items-center justify-between pt-4 border-t border-gray-100">
        <span class="text-sm text-gray-600">
          ${this.model.files ? this.model.files.length : 0} file${this.model.files && this.model.files.length !== 1 ? 's' : ''}
        </span>
        <div class="flex items-center space-x-2">
          <button 
            class="inline-flex items-center px-3 py-2 border border-gray-300 text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
            onclick="navigator.clipboard.writeText('${this.model.modelId}')"
            title="Copy model ID to clipboard"
            aria-label="Copy model ID ${this.model.modelId} to clipboard"
          >
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
            </svg>
            Copy ID
          </button>
          <a 
            href="https://huggingface.co/${this.model.modelId}" 
            target="_blank" 
            rel="noopener noreferrer"
            class="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
            aria-label="View ${this.model.modelId} on Hugging Face (opens in new tab)"
          >
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path>
            </svg>
            View Model
          </a>
        </div>
      </div>
    `;

    // Add keyboard navigation support
    this.setupKeyboardNavigation(card);
    
    // Add animation class for smooth appearance
    card.classList.add('animate-fade-in');
  }

  /**
   * Create formatted file list
   * @returns {string} HTML for file list
   */
  createFileList() {
    if (!this.model.files || this.model.files.length === 0) {
      return '<p class="text-gray-500 text-sm italic">No files available</p>';
    }

    return this.model.files.map(file => {
      const quantization = this.extractQuantization(file.filename);
      const highlightedFilename = this.options.showSearchHighlight ? 
        this.highlightSearchTerms(file.filename, this.options.searchQuery) : file.filename;
      
      return `
        <div class="flex items-center justify-between py-2 px-3 bg-gray-50 rounded text-sm hover:bg-gray-100 transition-colors group/file">
          <span class="font-mono text-gray-700 truncate flex-1 mr-2" title="${file.filename}">
            ${highlightedFilename}
          </span>
          <div class="flex items-center space-x-2 flex-shrink-0">
            ${quantization ? `<span class="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">${quantization}</span>` : ''}
            <button 
              class="opacity-0 group-hover/file:opacity-100 p-1 text-gray-400 hover:text-gray-600 transition-all"
              onclick="window.open('https://huggingface.co/${this.model.modelId}/resolve/main/${file.filename}', '_blank')"
              title="Download ${file.filename}"
              aria-label="Download ${file.filename}"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
              </svg>
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * Set up keyboard navigation for the card
   * @param {HTMLElement} card - Card element
   */
  setupKeyboardNavigation(card) {
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        // Focus on the main action button
        const viewButton = card.querySelector('a[href*="huggingface.co"]');
        if (viewButton) {
          viewButton.click();
        }
      }
    });

    // Add focus styles
    card.addEventListener('focus', () => {
      card.classList.add('ring-2', 'ring-blue-500', 'ring-offset-2');
    });

    card.addEventListener('blur', () => {
      card.classList.remove('ring-2', 'ring-blue-500', 'ring-offset-2');
    });
  }

  /**
   * Highlight search terms in text
   * @param {string} text - Text to highlight
   * @param {string} searchQuery - Search query
   * @returns {string} HTML with highlighted terms
   */
  highlightSearchTerms(text, searchQuery) {
    if (!searchQuery || !text) {
      return text;
    }
    
    const query = searchQuery.trim();
    if (query.length === 0) {
      return text;
    }
    
    try {
      const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(${escapedQuery})`, 'gi');
      return text.replace(regex, '<mark class="bg-yellow-200 px-1 rounded">$1</mark>');
    } catch (error) {
      console.warn('Error highlighting search terms:', error);
      return text;
    }
  }

  /**
   * Extract architecture from model ID
   * @param {string} modelId - Model identifier
   * @returns {string} Architecture name
   */
  extractArchitecture(modelId) {
    const parts = modelId.toLowerCase();
    if (parts.includes('llama')) return 'Llama';
    if (parts.includes('mistral')) return 'Mistral';
    if (parts.includes('phi')) return 'Phi';
    if (parts.includes('gemma')) return 'Gemma';
    if (parts.includes('dialogpt')) return 'DialoGPT';
    if (parts.includes('gpt')) return 'GPT';
    if (parts.includes('bert')) return 'BERT';
    if (parts.includes('t5')) return 'T5';
    if (parts.includes('falcon')) return 'Falcon';
    if (parts.includes('mpt')) return 'MPT';
    return 'Other';
  }

  /**
   * Extract quantization from filename
   * @param {string} filename - File name
   * @returns {string|null} Quantization type
   */
  extractQuantization(filename) {
    const match = filename.match(/\.(Q\d+_K_[MS]|Q\d+_\d+|F\d+|BF\d+)\.gguf$/i);
    return match ? match[1] : null;
  }

  /**
   * Format number with commas
   * @param {number} num - Number to format
   * @returns {string} Formatted number
   */
  formatNumber(num) {
    return num.toLocaleString();
  }

  /**
   * Create URL-friendly slug from model ID
   * @param {string} modelId - Model ID
   * @returns {string} URL slug
   */
  createModelSlug(modelId) {
    return modelId.replace('/', '--').replace(/[^a-zA-Z0-9-_]/g, '-').toLowerCase();
  }

  /**
   * Update card with new search highlighting
   * @param {string} searchQuery - New search query
   * @param {Object} searchResult - Search result data
   */
  updateSearchHighlight(searchQuery, searchResult = null) {
    this.options.searchQuery = searchQuery;
    this.options.searchResult = searchResult;
    this.options.showSearchHighlight = Boolean(searchQuery);
    
    if (this.element && this.isVisible) {
      this.renderCardContent(this.element);
    }
  }

  /**
   * Render method for compatibility with tests
   * @returns {HTMLElement} Model card element
   */
  render() {
    if (!this.element) {
      this.element = this.createElement();
    }
    return this.element;
  }

  /**
   * Update model data
   * @param {Object} newModel - New model data
   */
  updateModel(newModel) {
    this.model = newModel;
    if (this.element) {
      this.renderCardContent(this.element);
    }
  }

  /**
   * Get current model data
   * @returns {Object} Current model data
   */
  getModel() {
    return this.model;
  }

  /**
   * Format date for display (internal method for tests)
   * @param {string|Date} date - Date to format
   * @returns {string} Formatted date
   */
  _formatDate(date) {
    if (!date) return 'recently';
    
    try {
      const dateObj = new Date(date);
      if (isNaN(dateObj.getTime())) return 'recently';
      
      const now = new Date();
      const diffTime = Math.abs(now - dateObj);
      const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
      
      if (diffDays <= 1) return 'yesterday';
      if (diffDays < 7) return `${diffDays} days ago`;
      if (diffDays < 30) return `${Math.ceil(diffDays / 7)} weeks ago`;
      if (diffDays < 365) return `${Math.ceil(diffDays / 30)} months ago`;
      return `${Math.ceil(diffDays / 365)} years ago`;
    } catch (error) {
      return 'recently';
    }
  }

  /**
   * Destroy the card and clean up resources
   */
  destroy() {
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
    
    if (this.element && this.element.parentNode) {
      this.element.parentNode.removeChild(this.element);
    }
    
    this.element = null;
    this.model = null;
  }
}

export default ModelCard;