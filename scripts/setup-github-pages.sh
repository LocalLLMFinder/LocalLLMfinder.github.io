#!/bin/bash

# GGUF Model Index - Complete GitHub Pages Setup Script
# =====================================================
# This script configures everything needed for GitHub Pages deployment

set -e

echo ""
echo "🚀 Complete GitHub Pages Setup"
echo "=============================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Check prerequisites
print_info "Checking prerequisites..."

if ! command -v git &> /dev/null; then
    print_error "Git is not installed. Please install Git first."
    exit 1
fi

if ! command -v node &> /dev/null; then
    print_warning "Node.js not found. Some build optimizations may not work."
fi

print_status "Prerequisites checked"

# Verify we're in the right directory
if [ ! -f "index.html" ] || [ ! -f "main.js" ]; then
    print_error "This doesn't appear to be the GGUF Model Index directory."
    print_info "Please run this script from the project root directory."
    exit 1
fi

print_status "Project directory verified"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    print_info "Initializing Git repository..."
    git init
    print_status "Git repository initialized"
fi

# Check for GitHub remote
if ! git remote get-url origin &> /dev/null; then
    echo ""
    print_warning "No GitHub remote found."
    echo ""
    echo "Please follow these steps:"
    echo "1. Create a new repository on GitHub"
    echo "2. Copy the repository URL"
    echo ""
    read -p "Enter your GitHub repository URL: " REPO_URL
    
    if [ -z "$REPO_URL" ]; then
        print_error "Repository URL is required"
        exit 1
    fi
    
    git remote add origin "$REPO_URL"
    print_status "GitHub remote added"
else
    REPO_URL=$(git remote get-url origin)
    print_status "GitHub remote found: $REPO_URL"
fi

# Extract repository information
if [[ $REPO_URL =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
    USERNAME="${BASH_REMATCH[1]}"
    REPO_NAME="${BASH_REMATCH[2]}"
    GITHUB_PAGES_URL="https://${USERNAME}.github.io/${REPO_NAME}"
else
    print_error "Could not parse GitHub repository URL"
    exit 1
fi

print_info "Repository: $USERNAME/$REPO_NAME"
print_info "GitHub Pages URL: $GITHUB_PAGES_URL"

# Ask about custom domain
echo ""
read -p "Do you want to configure a custom domain? (y/n): " USE_CUSTOM_DOMAIN

if [[ $USE_CUSTOM_DOMAIN =~ ^[Yy]$ ]]; then
    read -p "Enter your custom domain (e.g., models.yourdomain.com): " CUSTOM_DOMAIN
    
    if [ ! -z "$CUSTOM_DOMAIN" ]; then
        echo "$CUSTOM_DOMAIN" > CNAME
        print_status "Created CNAME file for $CUSTOM_DOMAIN"
        
        # Provide DNS instructions
        echo ""
        print_info "DNS Configuration Required:"
        if [[ $CUSTOM_DOMAIN == *.*.* ]] || [[ $CUSTOM_DOMAIN == *www* ]]; then
            echo "Create CNAME record: $CUSTOM_DOMAIN -> $USERNAME.github.io"
        else
            echo "Create A records for $CUSTOM_DOMAIN pointing to:"
            echo "  185.199.108.153"
            echo "  185.199.109.153"
            echo "  185.199.110.153"
            echo "  185.199.111.153"
        fi
    fi
fi

# Ensure required files exist
print_info "Checking required files..."

# Create .nojekyll if it doesn't exist
if [ ! -f ".nojekyll" ]; then
    touch .nojekyll
    print_status "Created .nojekyll file"
fi

# Create 404.html if it doesn't exist
if [ ! -f "404.html" ]; then
    cat > 404.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Page Not Found - GGUF Model Index</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; padding: 50px; }
        h1 { color: #333; }
        p { color: #666; margin: 20px 0; }
        a { color: #0066cc; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>404 - Page Not Found</h1>
    <p>The page you're looking for doesn't exist.</p>
    <p><a href="/">Return to GGUF Model Index</a></p>
</body>
</html>
EOF
    print_status "Created 404.html page"
fi

# Create robots.txt if it doesn't exist
if [ ! -f "robots.txt" ]; then
    cat > robots.txt << 'EOF'
User-agent: *
Allow: /

Sitemap: https://USERNAME.github.io/REPO_NAME/sitemap.xml
EOF
    # Replace placeholders
    sed -i "s/USERNAME/$USERNAME/g" robots.txt
    sed -i "s/REPO_NAME/$REPO_NAME/g" robots.txt
    
    if [ ! -z "$CUSTOM_DOMAIN" ]; then
        sed -i "s|https://$USERNAME.github.io/$REPO_NAME|https://$CUSTOM_DOMAIN|g" robots.txt
    fi
    
    print_status "Created robots.txt"
fi

# Commit all changes
print_info "Committing configuration files..."

git add .
if ! git diff --staged --quiet; then
    git commit -m "Configure GitHub Pages deployment

- Add GitHub Pages workflow
- Configure security headers
- Set up custom domain support
- Add required static files"
    print_status "Configuration committed"
else
    print_info "No changes to commit"
fi

# Push to GitHub
print_info "Pushing to GitHub..."
git push -u origin main
print_status "Pushed to GitHub"

# Final instructions
echo ""
print_status "GitHub Pages Setup Complete!"
echo ""
print_info "Next Steps:"
echo "==========="
echo ""
echo "1. Go to your repository on GitHub:"
echo "   $REPO_URL"
echo ""
echo "2. Click Settings > Pages"
echo ""
echo "3. Under 'Source', select 'GitHub Actions'"
echo ""
echo "4. The site will be available at:"
if [ ! -z "$CUSTOM_DOMAIN" ]; then
    echo "   https://$CUSTOM_DOMAIN (after DNS configuration)"
    echo "   $GITHUB_PAGES_URL (GitHub Pages URL)"
else
    echo "   $GITHUB_PAGES_URL"
fi
echo ""

if [ ! -z "$CUSTOM_DOMAIN" ]; then
    echo "5. Configure DNS as shown above"
    echo ""
    echo "6. In GitHub Pages settings, add custom domain: $CUSTOM_DOMAIN"
    echo ""
    echo "7. Enable 'Enforce HTTPS' after DNS verification"
    echo ""
fi

print_info "The deployment workflow will run automatically on:"
echo "- Pushes to main branch"
echo "- Data updates from the scheduled workflow"
echo "- Manual triggers"
echo ""

print_status "Your GGUF Model Index is ready for GitHub Pages! 🎉"

# Optional: Open repository
if command -v open &> /dev/null; then
    read -p "Open repository in browser? (y/n): " OPEN_BROWSER
    if [[ $OPEN_BROWSER =~ ^[Yy]$ ]]; then
        open "$REPO_URL"
    fi
elif command -v xdg-open &> /dev/null; then
    read -p "Open repository in browser? (y/n): " OPEN_BROWSER
    if [[ $OPEN_BROWSER =~ ^[Yy]$ ]]; then
        xdg-open "$REPO_URL"
    fi
fi