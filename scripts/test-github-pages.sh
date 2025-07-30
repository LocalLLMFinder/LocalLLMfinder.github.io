#!/bin/bash

# GitHub Pages Compatibility Test Runner
# =====================================
# Runs comprehensive tests to verify GitHub Pages compatibility

set -e

echo ""
echo "🧪 GitHub Pages Compatibility Tests"
echo "==================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    print_error "This script must be run from the project root directory"
    exit 1
fi

print_info "Running GitHub Pages compatibility tests..."

# Run the test suite
echo ""
print_info "1. Running automated test suite..."

if npm test test-github-pages-compatibility.js; then
    print_status "Automated tests passed"
else
    print_error "Some automated tests failed"
    echo ""
    print_info "Check the test output above for details"
fi

# Manual checks
echo ""
print_info "2. Performing manual compatibility checks..."

# Check required files
echo ""
print_info "Checking required files..."

required_files=(".nojekyll" "404.html" "robots.txt" "index.html")
missing_files=()

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        print_status "$file exists"
    else
        print_warning "$file is missing"
        missing_files+=("$file")
    fi
done

# Check optional but recommended files
optional_files=("sitemap.xml" "CNAME")
for file in "${optional_files[@]}"; do
    if [ -f "$file" ]; then
        print_status "$file exists (optional)"
    else
        print_info "$file not found (optional)"
    fi
done

# Check data files
echo ""
print_info "Checking data files..."

data_files=("gguf_models.json" "gguf_models_estimated_sizes.json")
for file in "${data_files[@]}"; do
    if [ -f "$file" ]; then
        print_status "$file exists"
        
        # Validate JSON
        if jq empty "$file" 2>/dev/null; then
            print_status "$file is valid JSON"
        else
            print_error "$file contains invalid JSON"
        fi
    else
        print_warning "$file not found"
    fi
done

# Check data directory
if [ -d "data" ]; then
    print_status "data/ directory exists"
    
    data_json_files=("data/models.json" "data/search-index.json")
    for file in "${data_json_files[@]}"; do
        if [ -f "$file" ]; then
            print_status "$file exists"
            
            if jq empty "$file" 2>/dev/null; then
                print_status "$file is valid JSON"
            else
                print_error "$file contains invalid JSON"
            fi
        else
            print_warning "$file not found"
        fi
    done
else
    print_info "data/ directory not found (will be created by data pipeline)"
fi

# Check build output
echo ""
print_info "Checking build configuration..."

if [ -f "vite.config.js" ]; then
    print_status "Vite configuration found"
else
    print_warning "No Vite configuration found"
fi

if [ -f "package.json" ]; then
    print_status "package.json found"
    
    # Check for required scripts
    if grep -q '"build"' package.json; then
        print_status "Build script configured"
    else
        print_error "No build script found in package.json"
    fi
    
    if grep -q '"test"' package.json; then
        print_status "Test script configured"
    else
        print_warning "No test script found in package.json"
    fi
else
    print_error "package.json not found"
fi

# Check GitHub Actions workflows
echo ""
print_info "Checking GitHub Actions workflows..."

if [ -d ".github/workflows" ]; then
    print_status ".github/workflows directory exists"
    
    workflow_files=("deploy-pages.yml" "update-gguf-models.yml")
    for file in "${workflow_files[@]}"; do
        if [ -f ".github/workflows/$file" ]; then
            print_status "$file workflow exists"
        else
            print_warning "$file workflow not found"
        fi
    done
else
    print_error ".github/workflows directory not found"
fi

# Test build process
echo ""
print_info "3. Testing build process..."

if command -v npm &> /dev/null; then
    print_info "Installing dependencies..."
    if npm ci --silent; then
        print_status "Dependencies installed successfully"
        
        print_info "Running build..."
        if npm run build; then
            print_status "Build completed successfully"
            
            # Check build output
            if [ -d "dist" ]; then
                print_status "dist/ directory created"
                
                # Check critical files in dist
                critical_files=("dist/index.html")
                for file in "${critical_files[@]}"; do
                    if [ -f "$file" ]; then
                        print_status "$file exists in build output"
                    else
                        print_error "$file missing from build output"
                    fi
                done
                
                # Check assets directory
                if [ -d "dist/assets" ]; then
                    print_status "Assets directory exists in build"
                    
                    js_files=$(find dist/assets -name "*.js" | wc -l)
                    css_files=$(find dist/assets -name "*.css" | wc -l)
                    
                    print_info "Found $js_files JavaScript files and $css_files CSS files"
                else
                    print_warning "No assets directory in build output"
                fi
                
                # Calculate build size
                build_size=$(du -sh dist | cut -f1)
                print_info "Total build size: $build_size"
                
            else
                print_error "Build did not create dist/ directory"
            fi
        else
            print_error "Build failed"
        fi
    else
        print_error "Failed to install dependencies"
    fi
else
    print_warning "npm not found - skipping build test"
fi

# Test static file serving simulation
echo ""
print_info "4. Simulating static file serving..."

if [ -d "dist" ]; then
    # Check if files can be served statically
    print_info "Checking static file compatibility..."
    
    # Look for server-side dependencies
    if grep -r "require(" dist/ 2>/dev/null; then
        print_error "Found Node.js require() statements in build output"
    else
        print_status "No server-side dependencies found"
    fi
    
    # Check for absolute paths that might not work on GitHub Pages
    if grep -r "http://localhost" dist/ 2>/dev/null; then
        print_error "Found localhost references in build output"
    else
        print_status "No localhost references found"
    fi
    
    # Check for proper relative paths
    if grep -r "\.\./\.\." dist/ 2>/dev/null; then
        print_warning "Found complex relative paths - verify they work on GitHub Pages"
    else
        print_status "Path structure looks good"
    fi
else
    print_warning "No dist/ directory found - run build first"
fi

# Security checks
echo ""
print_info "5. Running security checks..."

# Check for sensitive information
sensitive_patterns=("password" "secret" "token" "api.*key")
found_sensitive=false

for pattern in "${sensitive_patterns[@]}"; do
    if grep -ri "$pattern" . --exclude-dir=node_modules --exclude-dir=.git --exclude="*.log" 2>/dev/null | grep -v "test-github-pages"; then
        print_warning "Found potential sensitive information: $pattern"
        found_sensitive=true
    fi
done

if [ "$found_sensitive" = false ]; then
    print_status "No sensitive information found in source code"
fi

# Check for HTTPS usage
if grep -r "http://" . --exclude-dir=node_modules --exclude-dir=.git 2>/dev/null | grep -v "localhost" | grep -v "test-github-pages"; then
    print_warning "Found HTTP URLs - consider using HTTPS"
else
    print_status "All external URLs use HTTPS"
fi

# Summary
echo ""
print_info "Test Summary"
echo "============"
echo ""

if [ ${#missing_files[@]} -eq 0 ]; then
    print_status "All required files are present"
else
    print_warning "Missing required files: ${missing_files[*]}"
fi

if [ -d "dist" ] && [ -f "dist/index.html" ]; then
    print_status "Build output is ready for GitHub Pages"
else
    print_warning "Build output may not be ready - run 'npm run build'"
fi

if [ -d ".github/workflows" ]; then
    print_status "GitHub Actions workflows are configured"
else
    print_warning "GitHub Actions workflows need to be set up"
fi

echo ""
print_info "Next steps:"
echo "1. Fix any issues identified above"
echo "2. Commit and push changes to GitHub"
echo "3. Enable GitHub Pages in repository settings"
echo "4. Monitor deployment in GitHub Actions"
echo ""

print_status "GitHub Pages compatibility test completed!"