/**
 * GGUF Model Discovery - Main Application Entry Point
 * 
 * This is the main entry point for the GGUF Model Discovery application.
 * It loads pre-generated JSON files and provides model discovery functionality.
 * NO API calls to Hugging Face are made from the frontend.
 * 
 * Task 3.3: Build JavaScript application core
 * Task 4.1: Create real-time search functionality
 * Requirements: 1.1, 1.3, 1.2, 6.1, 6.2
 */

import { searchEngine } from './services/SearchEngine.js';
import { debounceSearch } from './utils/debounce.js';
import { ModelCard } from './components/ModelCard.js';
import { seoManager } from './utils/seoManager.js';
import { Router } from './utils/router.js';
import { performanceOptimizer } from './utils/performanceOptimizer.js';
import { performanceMonitor } from './utils/performanceMonitor.js';
import { PerformanceDashboard } from './components/PerformanceDashboard.js';

/**
 * URL State Manager for bookmarkable filtered views
 * Requirements: 6.3
 */
class URLStateManager {
  constructor() {
    this.urlParams = new URLSearchParams(window.location.search);
  }

  /**
   * Update URL with current filter state
   * @param {Object} filterState - Current filter state
   * @param {string} searchQuery - Current search query
   */
  updateURL(filterState, searchQuery) {
    const params = new URLSearchParams();
    
    // Add search query
    if (searchQuery && searchQuery.trim()) {
      params.set('q', searchQuery.trim());
    }
    
    // Add filters
    if (filterState.quantization) {
      params.set('quantization', filterState.quantization);
    }
    if (filterState.architecture) {
      params.set('architecture', filterState.architecture);
    }
    if (filterState.sizeRange) {
      params.set('size', filterState.sizeRange);
    }
    if (filterState.sortBy && filterState.sortBy !== 'name') {
      params.set('sort', filterState.sortBy);
    }
    if (filterState.sortOrder && filterState.sortOrder !== 'asc') {
      params.set('order', filterState.sortOrder);
    }
    
    // Update URL without page reload
    const newURL = params.toString() ? 
      `${window.location.pathname}?${params.toString()}` : 
      window.location.pathname;
    
    window.history.replaceState({}, '', newURL);
  }

  /**
   * Load filter state from URL parameters
   * @returns {Object} Filter state from URL
   */
  loadFromURL() {
    return {
      searchQuery: this.urlParams.get('q') || '',
      quantization: this.urlParams.get('quantization') || '',
      architecture: this.urlParams.get('architecture') || '',
      sizeRange: this.urlParams.get('size') || '',
      sortBy: this.urlParams.get('sort') || 'name',
      sortOrder: this.urlParams.get('order') || 'asc'
    };
  }

  /**
   * Clear all URL parameters
   */
  clearURL() {
    window.history.replaceState({}, '', window.location.pathname);
  }
}

console.log('🧠 GGUF Model Discovery - Application Starting...');

/**
 * Model Discovery Application Class
 * Loads pre-generated JSON files and provides model discovery functionality
 * Requirements: 1.1, 1.3
 */
class ModelDiscoveryApp {
  constructor() {
    // Application State
    this.allModels = [];
    this.filteredModels = [];
    this.searchResults = [];
    this.currentPage = 1;
    this.modelsPerPage = 12;
    this.isLoading = false;
    this.searchQuery = '';
    this.sortBy = 'name';
    this.metadata = null;

    // DOM Elements
    this.searchInput = null;
    this.modelGrid = null;
    this.resultsCount = null;
    this.loadMoreButton = null;
    this.sortSelect = null;
    this.filterControls = null;

    // Search functionality with debouncing
    this.debouncedSearch = debounceSearch(this.performSearch.bind(this), 300);
    
    // Search state
    this.isSearchActive = false;
    this.lastSearchQuery = '';
    
    // Filter state
    this.activeFilters = {
      quantization: '',
      architecture: '',
      sizeRange: '',
      sortBy: 'name',
      sortOrder: 'asc'
    };
    
    // URL state management
    this.urlStateManager = new URLStateManager();
    
    // SEO Manager reference
    this.seoManager = seoManager;
    
    // Router for SEO-friendly URLs (initialized after DOM is ready)
    this.router = null;
  }

  /**
   * Initialize the application
   * Requirements: 1.1, 1.3
   */
  async init() {
    try {
      console.log('🔧 Initializing Model Discovery App...');

      // Set up DOM references
      this.setupDOMReferences();

      // Set up event listeners
      this.setupEventListeners();

      // Load model data from static JSON files (NO API calls to Hugging Face)
      await this.loadStaticModelData();

      // Initialize the UI with loaded data
      this.initializeUI();

      // Apply initial rendering
      this.renderModels();
      
      // Initialize router for SEO-friendly URLs
      this.router = new Router(this);

      console.log('✅ Model Discovery App initialized successfully');

    } catch (error) {
      console.error('❌ Failed to initialize application:', error);
      this.showError('Failed to initialize the application. Please refresh the page.');
    }
  }

  /**
   * Set up DOM element references
   */
  setupDOMReferences() {
    this.searchInput = document.getElementById('model-search');
    this.modelGrid = document.getElementById('model-grid');
    this.resultsCount = document.getElementById('results-count');
    this.loadMoreButton = document.getElementById('load-more');
    this.sortSelect = document.getElementById('sort-select');
    this.filterControls = document.getElementById('filter-controls');

    // Validate required elements
    const requiredElements = {
      'model-search': this.searchInput,
      'model-grid': this.modelGrid,
      'results-count': this.resultsCount,
      'sort-select': this.sortSelect,
      'filter-controls': this.filterControls
    };

    for (const [id, element] of Object.entries(requiredElements)) {
      if (!element) {
        throw new Error(`Required element not found: ${id}`);
      }
    }
  }

  /**
   * Set up event listeners
   */
  setupEventListeners() {
    // Search input with real-time search
    if (this.searchInput) {
      this.searchInput.addEventListener('input', (e) => {
        this.searchQuery = e.target.value.trim();
        this.debouncedSearch(this.searchQuery);
      });
      
      // Clear search on Escape key
      this.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          this.clearSearch();
        }
      });
    }

    // Sort select
    if (this.sortSelect) {
      this.sortSelect.addEventListener('change', (e) => {
        this.activeFilters.sortBy = e.target.value;
        this.sortBy = e.target.value; // Keep for backward compatibility
        this.sortModels();
        this.renderModels();
        this.updateURL();
      });
    }

    // Load more button
    if (this.loadMoreButton) {
      this.loadMoreButton.addEventListener('click', () => {
        this.loadMoreModels();
      });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      // Ctrl+K or Cmd+K to focus search
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        this.searchInput?.focus();
      }
    });

    // Handle browser back/forward buttons
    window.addEventListener('popstate', () => {
      this.urlStateManager = new URLStateManager();
      this.loadFiltersFromURL();
    });
  }

  /**
   * Load model data from static JSON files ONLY
   * NO API calls to Hugging Face from frontend
   * Requirements: 1.1, 1.3
   */
  async loadStaticModelData() {
    this.setLoading(true, 'Loading GGUF models...');

    try {
      console.log('📁 Loading models from static JSON files...');
      
      // Load the main models JSON file (generated by GitHub Actions)
      const response = await fetch('./gguf_models.json');
      
      if (!response.ok) {
        throw new Error(`Failed to load model data: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();

      // Handle both array format and object format with models property
      if (Array.isArray(data)) {
        this.allModels = data;
      } else if (data && Array.isArray(data.models)) {
        this.allModels = data.models;
        this.metadata = data.metadata || null;
      } else {
        throw new Error('Invalid model data format - expected array or object with models property');
      }

      console.log(`✅ Loaded ${this.allModels.length} models from static JSON`);

      // Load additional metadata if available and not already loaded
      if (!this.metadata) {
        try {
          const metadataResponse = await fetch('./gguf_models_estimated_sizes.json');
          if (metadataResponse.ok) {
            const sizeData = await metadataResponse.json();
            this.metadata = { estimatedSizes: sizeData };
            console.log('✅ Loaded model size estimates');
          }
        } catch (metadataError) {
          console.warn('⚠️ Could not load size metadata:', metadataError.message);
        }
      }

      // Load freshness indicators
      await this.loadFreshnessData();

      // Initialize search engine with loaded models
      searchEngine.indexModels(this.allModels);
      
      // Initialize filtered models with all models
      this.filteredModels = [...this.allModels];

      // Ensure zero network requests to external APIs during user visits
      console.log('🔒 All data loaded from static files - no external API calls made');

    } catch (error) {
      console.error('❌ Failed to load model data:', error);
      throw error;
    } finally {
      this.setLoading(false);
    }
  }

  /**
   * Load freshness data and initialize freshness indicators
   */
  async loadFreshnessData() {
    try {
      console.log('🕐 Loading freshness indicators...');
      const response = await fetch('./data/freshness_indicators.json');
      
      if (response.ok) {
        this.freshnessData = await response.json();
        console.log('✅ Loaded freshness indicators');
        this.initializeFreshnessIndicator();
      } else {
        console.warn('⚠️ Could not load freshness indicators, using fallback');
        this.createFallbackFreshnessData();
      }
    } catch (error) {
      console.warn('⚠️ Failed to load freshness data:', error.message);
      this.createFallbackFreshnessData();
    }
  }

  /**
   * Create fallback freshness data when indicators are not available
   */
  createFallbackFreshnessData() {
    const now = new Date();
    this.freshnessData = {
      lastSyncTimestamp: now.toISOString(),
      lastSyncFormatted: now.toISOString().replace('T', ' ').substring(0, 16) + ' UTC',
      hoursSinceSync: 0,
      overallStatus: 'unknown',
      statusColor: 'gray',
      statusIcon: '❓',
      timeMessage: 'Freshness data unavailable',
      freshnessScore: 0,
      totalModels: this.allModels ? this.allModels.length : 0,
      modelsWithTimestamps: 0,
      syncDuration: 0,
      syncMode: 'unknown',
      syncSuccess: true,
      stalenessWarnings: ['Freshness indicators could not be loaded'],
      showStalenessWarning: true
    };
    this.initializeFreshnessIndicator();
  }

  /**
   * Initialize the freshness indicator in the header
   */
  initializeFreshnessIndicator() {
    const container = document.getElementById('freshness-indicator-container');
    if (container && this.freshnessData) {
      // Import and initialize the freshness indicator
      import('./components/FreshnessIndicator.js').then(({ FreshnessIndicator }) => {
        this.freshnessIndicator = new FreshnessIndicator();
        const indicatorElement = this.freshnessIndicator.render(this.freshnessData);
        container.appendChild(indicatorElement);
        console.log('✅ Freshness indicator initialized');
      }).catch(error => {
        console.warn('⚠️ Could not initialize freshness indicator:', error);
      });
    }
  }

  /**
   * Initialize the UI components
   */
  initializeUI() {
    // Update results count and model count display
    this.updateResultsCount();
    this.updateModelCountDisplay();

    // Set up filter controls (basic implementation)
    this.setupFilterControls();

    // Hide loading screen
    this.hideLoadingScreen();
  }

  /**
   * Update the model count display in the header
   */
  updateModelCountDisplay() {
    const modelCountDisplay = document.getElementById('model-count-display');
    if (modelCountDisplay && this.allModels) {
      modelCountDisplay.innerHTML = `
        <span class="font-medium">Total Models:</span> 
        <span class="text-blue-600 font-semibold">${this.allModels.length.toLocaleString()}</span>
      `;
    }
  }

  /**
   * Set up enhanced filter controls with more options
   * Requirements: 6.1, 6.2, 6.3
   */
  setupFilterControls() {
    if (!this.filterControls) return;

    // Extract unique values for filters from loaded data
    const quantizations = [...new Set(
      this.allModels.flatMap(model => 
        model.files?.map(file => this.extractQuantization(file.filename)) || []
      )
    )].filter(Boolean).sort();

    const architectures = [...new Set(
      this.allModels.map(model => this.extractArchitecture(model.modelId))
    )].filter(Boolean).sort();

    // Calculate size ranges
    const sizeRanges = [
      { value: 'small', label: 'Small (< 4GB)', count: 0 },
      { value: 'medium', label: 'Medium (4-8GB)', count: 0 },
      { value: 'large', label: 'Large (8-16GB)', count: 0 },
      { value: 'xlarge', label: 'X-Large (> 16GB)', count: 0 }
    ];

    // Count models in each size range (approximate based on file count)
    this.allModels.forEach(model => {
      const fileCount = model.files ? model.files.length : 0;
      if (fileCount <= 2) sizeRanges[0].count++;
      else if (fileCount <= 4) sizeRanges[1].count++;
      else if (fileCount <= 6) sizeRanges[2].count++;
      else sizeRanges[3].count++;
    });

    // Create enhanced filter HTML
    this.filterControls.innerHTML = `
      <div class="filter-group">
        <label for="quantization-filter" class="block text-sm font-medium text-gray-700 mb-1">Quantization</label>
        <select id="quantization-filter" class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">All Quantizations</option>
          ${quantizations.map(q => `<option value="${q}">${q}</option>`).join('')}
        </select>
      </div>
      <div class="filter-group">
        <label for="architecture-filter" class="block text-sm font-medium text-gray-700 mb-1">Architecture</label>
        <select id="architecture-filter" class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">All Architectures</option>
          ${architectures.map(a => `<option value="${a}">${a}</option>`).join('')}
        </select>
      </div>
      <div class="filter-group">
        <label for="size-filter" class="block text-sm font-medium text-gray-700 mb-1">Model Size</label>
        <select id="size-filter" class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">All Sizes</option>
          ${sizeRanges.filter(r => r.count > 0).map(r => 
            `<option value="${r.value}">${r.label} (${r.count})</option>`
          ).join('')}
        </select>
      </div>
      <div class="filter-group">
        <label for="sort-order-filter" class="block text-sm font-medium text-gray-700 mb-1">Sort Order</label>
        <select id="sort-order-filter" class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="asc">Ascending</option>
          <option value="desc">Descending</option>
        </select>
      </div>
      <div class="filter-group flex items-end">
        <button id="clear-filters-btn" class="w-full px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-medium rounded-md border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors">
          Clear All Filters
        </button>
      </div>
    `;

    // Add filter event listeners
    const quantizationFilter = document.getElementById('quantization-filter');
    const architectureFilter = document.getElementById('architecture-filter');
    const sizeFilter = document.getElementById('size-filter');
    const sortOrderFilter = document.getElementById('sort-order-filter');
    const clearFiltersBtn = document.getElementById('clear-filters-btn');

    if (quantizationFilter) {
      quantizationFilter.addEventListener('change', (e) => {
        this.activeFilters.quantization = e.target.value;
        this.applyFilters();
      });
    }
    if (architectureFilter) {
      architectureFilter.addEventListener('change', (e) => {
        this.activeFilters.architecture = e.target.value;
        this.applyFilters();
      });
    }
    if (sizeFilter) {
      sizeFilter.addEventListener('change', (e) => {
        this.activeFilters.sizeRange = e.target.value;
        this.applyFilters();
      });
    }
    if (sortOrderFilter) {
      sortOrderFilter.addEventListener('change', (e) => {
        this.activeFilters.sortOrder = e.target.value;
        this.sortModels();
        this.renderModels();
        this.updateURL();
      });
    }
    if (clearFiltersBtn) {
      clearFiltersBtn.addEventListener('click', () => {
        this.clearAllFilters();
      });
    }

    // Load initial state from URL
    this.loadFiltersFromURL();
  }

  /**
   * Extract quantization from filename
   */
  extractQuantization(filename) {
    const match = filename.match(/\.(Q\d+_K_[MS]|Q\d+_\d+|F\d+|BF\d+)\.gguf$/i);
    return match ? match[1] : null;
  }

  /**
   * Extract architecture from model ID
   */
  extractArchitecture(modelId) {
    const parts = modelId.toLowerCase();
    if (parts.includes('llama')) return 'Llama';
    if (parts.includes('mistral')) return 'Mistral';
    if (parts.includes('phi')) return 'Phi';
    if (parts.includes('dialogpt')) return 'DialoGPT';
    if (parts.includes('gpt')) return 'GPT';
    if (parts.includes('bert')) return 'BERT';
    return 'Other';
  }

  /**
   * Perform search using SearchEngine
   * Requirements: 1.2, 6.1, 6.2
   */
  performSearch(query) {
    console.log('🔍 Performing search for:', query);
    
    // Update search state
    this.isSearchActive = query && query.length > 0;
    this.lastSearchQuery = query;
    
    if (this.isSearchActive) {
      // Use SearchEngine for fast text search
      const searchResults = searchEngine.search(query);
      this.searchResults = searchResults;
      
      // Extract models from search results for filtering
      const searchedModels = searchResults.map(result => result.model);
      
      // Apply additional filters to search results
      this.filteredModels = this.applyAdditionalFilters(searchedModels);
      
      console.log(`📊 Search found ${searchResults.length} results, ${this.filteredModels.length} after filters`);
    } else {
      // No search query - show all models with filters applied
      this.searchResults = [];
      this.filteredModels = this.applyAdditionalFilters(this.allModels);
    }

    // Reset pagination and render
    this.currentPage = 1;
    this.sortModels();
    this.renderModels();
    
    // Update SEO meta tags for search results
    this.updateSearchSEO(query, this.filteredModels.length);
  }

  /**
   * Apply additional filters (non-search filters) to model list
   * Requirements: 6.1, 6.2
   * @param {Array} models - Models to filter
   * @returns {Array} Filtered models
   */
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

      // Size range filter (approximate based on file count)
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
            matchesSize = fileCount > 4 && fileCount <= 6;
            break;
          case 'xlarge':
            matchesSize = fileCount > 6;
            break;
          default:
            matchesSize = true;
        }
        
        if (!matchesSize) return false;
      }

      return true;
    });
  }

  /**
   * Apply all filters (search + additional filters)
   * Requirements: 6.1, 6.2, 6.3
   */
  applyFilters() {
    // Trigger search with current query (which will also apply additional filters)
    this.performSearch(this.searchQuery);
    
    // Update URL state for bookmarkable views
    this.updateURL();
  }

  /**
   * Load filters from URL parameters
   * Requirements: 6.3
   */
  loadFiltersFromURL() {
    const urlState = this.urlStateManager.loadFromURL();
    
    // Set search query
    if (urlState.searchQuery) {
      this.searchQuery = urlState.searchQuery;
      if (this.searchInput) {
        this.searchInput.value = urlState.searchQuery;
      }
    }
    
    // Set filter values
    this.activeFilters.quantization = urlState.quantization;
    this.activeFilters.architecture = urlState.architecture;
    this.activeFilters.sizeRange = urlState.sizeRange;
    this.activeFilters.sortBy = urlState.sortBy;
    this.activeFilters.sortOrder = urlState.sortOrder;
    
    // Update UI elements
    const quantizationFilter = document.getElementById('quantization-filter');
    const architectureFilter = document.getElementById('architecture-filter');
    const sizeFilter = document.getElementById('size-filter');
    const sortOrderFilter = document.getElementById('sort-order-filter');
    
    if (quantizationFilter) quantizationFilter.value = urlState.quantization;
    if (architectureFilter) architectureFilter.value = urlState.architecture;
    if (sizeFilter) sizeFilter.value = urlState.sizeRange;
    if (sortOrderFilter) sortOrderFilter.value = urlState.sortOrder;
    if (this.sortSelect) this.sortSelect.value = urlState.sortBy;
    
    // Apply filters if any are set
    if (urlState.searchQuery || urlState.quantization || urlState.architecture || 
        urlState.sizeRange || urlState.sortBy !== 'name' || urlState.sortOrder !== 'asc') {
      this.applyFilters();
    }
  }

  /**
   * Update URL with current filter state
   * Requirements: 6.3
   */
  updateURL() {
    this.urlStateManager.updateURL(this.activeFilters, this.searchQuery);
  }

  /**
   * Clear all filters and reset to default state
   */
  clearAllFilters() {
    // Reset filter state
    this.activeFilters = {
      quantization: '',
      architecture: '',
      sizeRange: '',
      sortBy: 'name',
      sortOrder: 'asc'
    };
    
    // Clear search
    this.clearSearch();
    
    // Reset UI elements
    const quantizationFilter = document.getElementById('quantization-filter');
    const architectureFilter = document.getElementById('architecture-filter');
    const sizeFilter = document.getElementById('size-filter');
    const sortOrderFilter = document.getElementById('sort-order-filter');
    
    if (quantizationFilter) quantizationFilter.value = '';
    if (architectureFilter) architectureFilter.value = '';
    if (sizeFilter) sizeFilter.value = '';
    if (sortOrderFilter) sortOrderFilter.value = 'asc';
    if (this.sortSelect) this.sortSelect.value = 'name';
    
    // Clear URL
    this.urlStateManager.clearURL();
    
    // Apply filters (which will show all models)
    this.applyFilters();
    
    console.log('🗑️ All filters cleared');
  }

  /**
   * Clear search and reset to all models
   */
  clearSearch() {
    this.searchQuery = '';
    this.searchInput.value = '';
    this.isSearchActive = false;
    this.lastSearchQuery = '';
    this.searchResults = [];
    
    // Cancel any pending debounced search
    this.debouncedSearch.cancel();
    
    // Apply filters to all models
    this.applyFilters();
    
    console.log('🗑️ Search cleared');
  }

  /**
   * Handle search input (legacy method - now uses performSearch)
   */
  handleSearch() {
    this.performSearch(this.searchQuery);
  }

  /**
   * Sort models based on current sort criteria with order support
   * Requirements: 6.1, 6.2
   */
  sortModels() {
    const sortBy = this.activeFilters.sortBy || this.sortBy;
    const sortOrder = this.activeFilters.sortOrder || 'asc';
    
    this.filteredModels.sort((a, b) => {
      let comparison = 0;
      
      switch (sortBy) {
        case 'name':
          comparison = a.modelId.localeCompare(b.modelId);
          break;
        case 'downloads':
          comparison = (a.downloads || 0) - (b.downloads || 0);
          break;
        case 'updated':
          comparison = new Date(a.lastModified || 0) - new Date(b.lastModified || 0);
          break;
        case 'size':
          // Sort by number of files as a proxy for size variety
          comparison = (a.files?.length || 0) - (b.files?.length || 0);
          break;
        case 'popularity':
          // Sort by downloads (alias for downloads)
          comparison = (a.downloads || 0) - (b.downloads || 0);
          break;
        default:
          comparison = 0;
      }
      
      // Apply sort order
      return sortOrder === 'desc' ? -comparison : comparison;
    });
  }

  /**
   * Render models to the grid
   * Requirements: 1.3
   */
  renderModels() {
    if (!this.modelGrid) return;

    // Calculate models to show
    const startIndex = 0;
    const endIndex = this.currentPage * this.modelsPerPage;
    const modelsToShow = this.filteredModels.slice(startIndex, endIndex);

    // Clear grid
    this.modelGrid.innerHTML = '';

    if (modelsToShow.length === 0) {
      this.modelGrid.innerHTML = `
        <div class="col-span-full text-center py-12">
          <div class="text-gray-400 mb-4">
            <svg class="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6-4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.29-1.009-5.824-2.562M15 6.306a7.962 7.962 0 00-6 0m6 0V5a2 2 0 00-2-2H9a2 2 0 00-2 2v1.306m6 0V7a2 2 0 012 2v4M9 6.306V7a2 2 0 00-2-2H7a2 2 0 00-2 2v4.01M15 6.306V7a2 2 0 012 2v4.01"></path>
            </svg>
          </div>
          <h3 class="text-lg font-medium text-gray-900 mb-2">No models found</h3>
          <p class="text-gray-600">Try adjusting your search or filter criteria.</p>
        </div>
      `;
      this.updateLoadMoreButton(false);
      this.updateResultsCount();
      return;
    }

    // Render model cards using the ModelCard component
    modelsToShow.forEach(model => {
      // Find search result data for this model
      const searchResult = this.isSearchActive ? 
        this.searchResults.find(result => result.model.modelId === model.modelId) : null;

      // Create model card with enhanced options
      const modelCard = new ModelCard(model, {
        lazyLoad: true,
        showSearchHighlight: this.isSearchActive,
        searchQuery: this.searchQuery,
        searchResult: searchResult
      });

      const cardElement = modelCard.createElement();
      this.modelGrid.appendChild(cardElement);
    });

    // Update load more button
    const hasMore = endIndex < this.filteredModels.length;
    this.updateLoadMoreButton(hasMore);

    // Update results count
    this.updateResultsCount();
  }

  /**
   * Create a model card element with search highlighting
   * Requirements: 1.3, 1.2, 6.1
   */
  createModelCard(model) {
    const card = document.createElement('div');
    card.className = 'bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow relative';
    card.setAttribute('role', 'article');
    card.setAttribute('aria-label', `Model: ${model.modelId}`);

    // Find search result data for highlighting
    const searchResult = this.isSearchActive ? 
      this.searchResults.find(result => result.model.modelId === model.modelId) : null;

    // Extract model name and organization with highlighting
    const [org, ...nameParts] = model.modelId.split('/');
    const modelName = nameParts.join('/') || org;
    const organization = nameParts.length > 0 ? org : '';

    // Apply search highlighting
    const highlightedModelName = this.highlightSearchTerms(modelName, this.searchQuery);
    const highlightedOrganization = this.highlightSearchTerms(organization, this.searchQuery);

    // Format download count
    const downloadCount = model.downloads ? this.formatNumber(model.downloads) : 'N/A';

    // Format last modified date
    const lastModified = model.lastModified ? 
      new Date(model.lastModified).toLocaleDateString() : 'N/A';

    // Create file list
    const fileList = model.files ? model.files.map(file => {
      const quantization = this.extractQuantization(file.filename);
      return `
        <div class="flex items-center justify-between py-2 px-3 bg-gray-50 rounded text-sm">
          <span class="font-mono text-gray-700">${file.filename}</span>
          ${quantization ? `<span class="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">${quantization}</span>` : ''}
        </div>
      `;
    }).join('') : '<p class="text-gray-500 text-sm">No files available</p>';

    // Add search score indicator if this is a search result
    const searchScoreIndicator = searchResult && searchResult.score > 1 ? 
      `<div class="absolute top-2 right-2 bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full">
        Match: ${Math.round(searchResult.score * 10) / 10}
      </div>` : '';

    card.innerHTML = `
      ${searchScoreIndicator}
      <div class="flex items-start justify-between mb-4">
        <div class="flex-1 min-w-0">
          <h3 class="text-lg font-semibold text-gray-900 truncate" title="${model.modelId}">
            ${highlightedModelName}
          </h3>
          ${organization ? `<p class="text-sm text-gray-600">${highlightedOrganization}</p>` : ''}
        </div>
        <div class="flex-shrink-0 ml-4">
          <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            ${this.highlightSearchTerms(this.extractArchitecture(model.modelId), this.searchQuery)}
          </span>
        </div>
      </div>

      <div class="mb-4">
        <div class="flex items-center text-sm text-gray-600 space-x-4">
          <div class="flex items-center">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"></path>
            </svg>
            ${downloadCount} downloads
          </div>
          <div class="flex items-center">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            ${lastModified}
          </div>
        </div>
      </div>

      <div class="mb-4">
        <h4 class="text-sm font-medium text-gray-900 mb-2">Available Files:</h4>
        <div class="space-y-1 max-h-32 overflow-y-auto">
          ${fileList}
        </div>
      </div>

      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-600">
          ${model.files ? model.files.length : 0} file${model.files && model.files.length !== 1 ? 's' : ''}
        </span>
        <a 
          href="https://huggingface.co/${model.modelId}" 
          target="_blank" 
          rel="noopener noreferrer"
          class="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
          aria-label="View ${model.modelId} on Hugging Face"
        >
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path>
          </svg>
          View Model
        </a>
      </div>
    `;

    return card;
  }

  /**
   * Load more models (pagination)
   */
  loadMoreModels() {
    this.currentPage++;
    this.renderModels();
  }

  /**
   * Update the load more button visibility
   */
  updateLoadMoreButton(hasMore) {
    if (!this.loadMoreButton) return;

    if (hasMore) {
      this.loadMoreButton.classList.remove('hidden');
      this.loadMoreButton.disabled = false;
    } else {
      this.loadMoreButton.classList.add('hidden');
    }
  }

  /**
   * Update results count display with search information
   */
  updateResultsCount() {
    if (!this.resultsCount) return;

    const showing = Math.min(this.currentPage * this.modelsPerPage, this.filteredModels.length);
    const total = this.filteredModels.length;
    const totalModels = this.allModels.length;

    let countText = '';
    
    if (this.isSearchActive) {
      // Show search results count
      const searchResultsCount = this.searchResults.length;
      if (total === searchResultsCount) {
        countText = `Showing ${showing} of ${total} search results for "${this.lastSearchQuery}"`;
      } else {
        countText = `Showing ${showing} of ${total} filtered results (${searchResultsCount} search results for "${this.lastSearchQuery}")`;
      }
    } else {
      // Show regular filter results
      if (total === totalModels) {
        countText = `Showing ${showing} of ${total} models`;
      } else {
        countText = `Showing ${showing} of ${total} models (filtered from ${totalModels} total)`;
      }
    }
    
    this.resultsCount.textContent = countText;
    
    // Add search performance info if available
    if (this.isSearchActive && this.searchResults.length > 0) {
      const searchStats = searchEngine.getSearchStats();
      if (searchStats.lastSearchTime > 0) {
        const perfInfo = document.createElement('span');
        perfInfo.className = 'text-xs text-gray-500 ml-2';
        perfInfo.textContent = `(${searchStats.lastSearchTime.toFixed(1)}ms)`;
        this.resultsCount.appendChild(perfInfo);
      }
    }

    // Update active filters display
    this.updateActiveFiltersDisplay();
  }

  /**
   * Update the display of active filters
   * Requirements: 6.1, 6.2
   */
  updateActiveFiltersDisplay() {
    const activeFiltersContainer = document.getElementById('active-filters');
    if (!activeFiltersContainer) return;

    const activeFilterTags = [];

    // Add search query tag
    if (this.isSearchActive && this.lastSearchQuery) {
      activeFilterTags.push({
        type: 'search',
        label: `Search: "${this.lastSearchQuery}"`,
        value: this.lastSearchQuery
      });
    }

    // Add filter tags
    if (this.activeFilters.quantization) {
      activeFilterTags.push({
        type: 'quantization',
        label: `Quantization: ${this.activeFilters.quantization}`,
        value: this.activeFilters.quantization
      });
    }

    if (this.activeFilters.architecture) {
      activeFilterTags.push({
        type: 'architecture',
        label: `Architecture: ${this.activeFilters.architecture}`,
        value: this.activeFilters.architecture
      });
    }

    if (this.activeFilters.sizeRange) {
      const sizeLabels = {
        small: 'Small (< 4GB)',
        medium: 'Medium (4-8GB)',
        large: 'Large (8-16GB)',
        xlarge: 'X-Large (> 16GB)'
      };
      activeFilterTags.push({
        type: 'size',
        label: `Size: ${sizeLabels[this.activeFilters.sizeRange]}`,
        value: this.activeFilters.sizeRange
      });
    }

    // Add sort tag if not default
    if (this.activeFilters.sortBy !== 'name' || this.activeFilters.sortOrder !== 'asc') {
      const sortLabel = `Sort: ${this.activeFilters.sortBy} (${this.activeFilters.sortOrder})`;
      activeFilterTags.push({
        type: 'sort',
        label: sortLabel,
        value: `${this.activeFilters.sortBy}-${this.activeFilters.sortOrder}`
      });
    }

    // Render filter tags
    activeFiltersContainer.innerHTML = activeFilterTags.map(tag => `
      <span class="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-100 text-blue-800">
        ${tag.label}
        <button 
          class="ml-2 text-blue-600 hover:text-blue-800 focus:outline-none"
          onclick="window.modelDiscoveryApp.removeFilter('${tag.type}', '${tag.value}')"
          aria-label="Remove ${tag.label} filter"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </span>
    `).join('');
  }

  /**
   * Remove a specific filter
   * @param {string} filterType - Type of filter to remove
   * @param {string} filterValue - Value of filter to remove
   */
  removeFilter(filterType, filterValue) {
    switch (filterType) {
      case 'search':
        this.clearSearch();
        break;
      case 'quantization':
        this.activeFilters.quantization = '';
        const quantizationFilter = document.getElementById('quantization-filter');
        if (quantizationFilter) quantizationFilter.value = '';
        break;
      case 'architecture':
        this.activeFilters.architecture = '';
        const architectureFilter = document.getElementById('architecture-filter');
        if (architectureFilter) architectureFilter.value = '';
        break;
      case 'size':
        this.activeFilters.sizeRange = '';
        const sizeFilter = document.getElementById('size-filter');
        if (sizeFilter) sizeFilter.value = '';
        break;
      case 'sort':
        this.activeFilters.sortBy = 'name';
        this.activeFilters.sortOrder = 'asc';
        if (this.sortSelect) this.sortSelect.value = 'name';
        const sortOrderFilter = document.getElementById('sort-order-filter');
        if (sortOrderFilter) sortOrderFilter.value = 'asc';
        break;
    }

    this.applyFilters();
  }

  /**
   * Set loading state
   */
  setLoading(isLoading, message = 'Loading...') {
    this.isLoading = isLoading;
    
    const globalLoading = document.getElementById('global-loading');
    const loadingMessage = document.getElementById('loading-message');
    
    if (globalLoading) {
      if (isLoading) {
        globalLoading.classList.remove('hidden');
        if (loadingMessage) {
          loadingMessage.textContent = message;
        }
      } else {
        globalLoading.classList.add('hidden');
      }
    }
  }

  /**
   * Hide the initial loading screen
   */
  hideLoadingScreen() {
    const loadingScreen = document.getElementById('loading-screen');
    if (loadingScreen) {
      loadingScreen.style.opacity = '0';
      loadingScreen.style.transition = 'opacity 0.3s ease-out';
      setTimeout(() => {
        loadingScreen.style.display = 'none';
      }, 300);
    }
  }

  /**
   * Show error message
   */
  showError(message) {
    const errorContainer = document.getElementById('error-toast-container');
    if (!errorContainer) {
      console.error('Error container not found, showing alert:', message);
      alert(message);
      return;
    }

    const errorToast = document.createElement('div');
    errorToast.className = 'bg-red-50 border border-red-200 rounded-lg p-4 shadow-lg';
    errorToast.setAttribute('role', 'alert');
    errorToast.innerHTML = `
      <div class="flex items-start">
        <div class="flex-shrink-0">
          <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
          </svg>
        </div>
        <div class="ml-3 flex-1">
          <p class="text-sm font-medium text-red-800">${message}</p>
        </div>
        <div class="ml-auto pl-3">
          <button class="inline-flex text-red-400 hover:text-red-600" onclick="this.parentElement.parentElement.parentElement.remove()">
            <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
          </button>
        </div>
      </div>
    `;

    errorContainer.appendChild(errorToast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
      if (errorToast.parentNode) {
        errorToast.remove();
      }
    }, 5000);
  }

  /**
   * Format number with commas
   */
  formatNumber(num) {
    return num.toLocaleString();
  }

  /**
   * Highlight search terms in text
   * @param {string} text - Text to highlight
   * @param {string} searchQuery - Search query to highlight
   * @returns {string} HTML with highlighted terms
   */
  highlightSearchTerms(text, searchQuery) {
    if (!searchQuery || !text || !this.isSearchActive) {
      return text;
    }
    
    const query = searchQuery.trim();
    if (query.length === 0) {
      return text;
    }
    
    // Escape special regex characters in the search query
    const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    
    try {
      // Create case-insensitive regex for highlighting
      const regex = new RegExp(`(${escapedQuery})`, 'gi');
      return text.replace(regex, '<mark class="bg-yellow-200 px-1 rounded">$1</mark>');
    } catch (error) {
      console.warn('Error highlighting search terms:', error);
      return text;
    }
  }

  /**
   * Get search statistics for debugging
   * @returns {Object} Search statistics
   */
  getSearchStats() {
    return {
      ...searchEngine.getSearchStats(),
      isSearchActive: this.isSearchActive,
      searchQuery: this.searchQuery,
      searchResultsCount: this.searchResults.length,
      filteredResultsCount: this.filteredModels.length
    };
  }

  /**
   * Debounce utility function (legacy - now using imported debounce)
   */
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  /**
   * Update SEO meta tags for search results
   * @param {string} query - Search query
   * @param {number} resultCount - Number of results found
   */
  updateSearchSEO(query, resultCount) {
    if (query && query.trim()) {
      const meta = seoManager.generateSearchPageMeta(query, resultCount);
      seoManager.updateMetaTags(meta);
      
      // Update breadcrumbs for search
      const breadcrumbs = [
        { name: 'Home', url: '/' },
        { name: `Search: "${query}"` }
      ];
      seoManager.updateBreadcrumbs(breadcrumbs);
      
      // Generate search results structured data
      const searchStructuredData = seoManager.generateSearchResultsStructuredData(
        query, 
        this.filteredModels.slice(0, 10), 
        resultCount
      );
      seoManager.updateStructuredData('search-results-data', searchStructuredData);
    } else {
      // Reset to default meta tags when no search
      const meta = seoManager.generateSearchPageMeta('', resultCount);
      seoManager.updateMetaTags(meta);
      
      // Reset breadcrumbs
      const breadcrumbs = [
        { name: 'Home', url: '/' },
        { name: 'GGUF Models' }
      ];
      seoManager.updateBreadcrumbs(breadcrumbs);
    }
  }

  /**
   * Update SEO for individual model view
   * @param {Object} model - Model data
   */
  updateModelSEO(model) {
    const meta = seoManager.generateModelPageMeta(model);
    seoManager.updateMetaTags(meta);
    
    // Update breadcrumbs for model page
    const breadcrumbs = [
      { name: 'Home', url: '/' },
      { name: 'Models', url: '/' },
      { name: model.family || 'Unknown', url: `/family/${(model.family || 'unknown').toLowerCase()}` },
      { name: model.name || model.id }
    ];
    seoManager.updateBreadcrumbs(breadcrumbs);
  }

  /**
   * Update SEO for family view
   * @param {string} family - Family name
   * @param {number} modelCount - Number of models in family
   */
  updateFamilySEO(family, modelCount) {
    const meta = seoManager.generateFamilyPageMeta(family, modelCount);
    seoManager.updateMetaTags(meta);
    
    // Update breadcrumbs for family page
    const breadcrumbs = [
      { name: 'Home', url: '/' },
      { name: 'Models', url: '/' },
      { name: `${family} Models` }
    ];
    seoManager.updateBreadcrumbs(breadcrumbs);
  }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', async () => {
  try {
    // Initialize performance optimizations first
    console.log('🚀 Initializing performance optimizations...');
    
    const app = new ModelDiscoveryApp();
    await app.init();
    
    // Initialize performance dashboard
    const performanceDashboard = new PerformanceDashboard(performanceMonitor);
    
    // Report initial performance metrics
    setTimeout(() => {
      performanceOptimizer.reportPerformanceMetrics();
      performanceMonitor.generateReport();
    }, 2000);
    
    // Make app globally available for debugging
    window.modelDiscoveryApp = app;
    window.performanceOptimizer = performanceOptimizer;
    window.performanceMonitor = performanceMonitor;
    window.performanceDashboard = performanceDashboard;
    
  } catch (error) {
    console.error('❌ Failed to start application:', error);
    
    // Show error in loading screen
    const loadingScreen = document.getElementById('loading-screen');
    if (loadingScreen) {
      loadingScreen.innerHTML = `
        <div class="text-center">
          <div class="text-red-600 mb-4">
            <svg class="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
            </svg>
          </div>
          <h1 class="text-2xl font-bold text-gray-900 mb-2">Application Error</h1>
          <p class="text-gray-600 mb-4">Failed to load the GGUF Model Index.</p>
          <button onclick="window.location.reload()" class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
            Reload Application
          </button>
        </div>
      `;
    }
  }
});

// Handle global errors gracefully
window.addEventListener('error', (event) => {
  console.error('Global error:', event.error);
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason);
  event.preventDefault();
});

console.log('✅ GGUF Model Discovery - Application script loaded');