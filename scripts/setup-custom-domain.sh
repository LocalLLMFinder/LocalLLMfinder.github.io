#!/bin/bash

# GGUF Model Index - Custom Domain Setup Script
# ==============================================
# This script helps configure a custom domain for GitHub Pages

set -e

echo ""
echo "🌐 Custom Domain Setup for GitHub Pages"
echo "======================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Get domain from user
echo "Enter your custom domain (e.g., models.yourdomain.com or yourdomain.com):"
read -p "Domain: " DOMAIN

if [ -z "$DOMAIN" ]; then
    echo "❌ Domain is required"
    exit 1
fi

# Validate domain format
if [[ ! $DOMAIN =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?\.[a-zA-Z]{2,}$ ]]; then
    print_warning "Domain format may be invalid. Please double-check: $DOMAIN"
fi

# Create CNAME file
echo "$DOMAIN" > CNAME
print_status "Created CNAME file with domain: $DOMAIN"

# Determine if it's an apex domain or subdomain
if [[ $DOMAIN == *.* ]] && [[ ! $DOMAIN == *.*.* ]]; then
    DOMAIN_TYPE="apex"
else
    DOMAIN_TYPE="subdomain"
fi

# Provide DNS configuration instructions
echo ""
print_info "DNS Configuration Instructions"
echo "=============================="
echo ""

if [ "$DOMAIN_TYPE" = "apex" ]; then
    echo "For apex domain ($DOMAIN), create these A records:"
    echo "  185.199.108.153"
    echo "  185.199.109.153"
    echo "  185.199.110.153"
    echo "  185.199.111.153"
    echo ""
    echo "Also create a CNAME record for www subdomain:"
    echo "  www.$DOMAIN -> $(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^/]*\)\/\([^.]*\).*/\1.github.io/')"
else
    echo "For subdomain ($DOMAIN), create this CNAME record:"
    echo "  $DOMAIN -> $(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^/]*\)\/\([^.]*\).*/\1.github.io/')"
fi

echo ""
print_info "GitHub Repository Configuration"
echo "==============================="
echo ""
echo "After configuring DNS:"
echo "1. Go to your repository Settings > Pages"
echo "2. Enter '$DOMAIN' in the Custom domain field"
echo "3. Enable 'Enforce HTTPS' (recommended)"
echo "4. Wait for DNS verification (may take up to 24 hours)"

# Commit CNAME file
echo ""
print_info "Committing CNAME file..."

git add CNAME
git commit -m "Add custom domain: $DOMAIN"
git push

print_status "CNAME file committed and pushed"

echo ""
print_status "Custom domain setup complete!"
echo ""
print_info "Next steps:"
echo "1. Configure DNS as shown above"
echo "2. Update GitHub Pages settings"
echo "3. Wait for DNS propagation"
echo "4. Test your custom domain"
echo ""