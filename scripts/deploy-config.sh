#!/bin/bash
# Configuration Deployment Script for Unix/Linux/macOS
# Provides easy deployment and management of sync configurations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration directories
CONFIG_DIR="$PROJECT_ROOT/config"
BACKUP_DIR="$CONFIG_DIR/backups"

# Ensure directories exist
mkdir -p "$CONFIG_DIR" "$BACKUP_DIR"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
Configuration Deployment Script

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    deploy <environment>     Deploy configuration for environment
    create <environment>     Create new environment configuration
    validate                 Validate all configurations
    list                     List available configurations
    compare <config1> <config2>  Compare two configurations
    backup                   Backup current configuration
    restore <backup_file>    Restore from backup
    help                     Show this help message

Environments:
    development             Development environment
    staging                 Staging environment  
    production              Production environment

Options:
    --source <file>         Source configuration file for deploy
    --no-validate          Skip validation during deploy
    --no-backup            Skip backup during deploy
    --force                Force operation without confirmation

Examples:
    $0 deploy production
    $0 deploy staging --source config/custom-config.yaml
    $0 create development
    $0 validate
    $0 list
    $0 compare sync-config-development.yaml sync-config-production.yaml
    $0 backup
    $0 restore sync-config_backup_20240130_143022.yaml

EOF
}

# Validate environment
validate_environment() {
    local env="$1"
    case "$env" in
        development|staging|production|testing)
            return 0
            ;;
        *)
            error "Invalid environment: $env"
            error "Valid environments: development, staging, production, testing"
            return 1
            ;;
    esac
}

# Deploy configuration
deploy_config() {
    local environment="$1"
    local source_config="$2"
    local validate_flag="$3"
    local backup_flag="$4"
    local force_flag="$5"
    
    log "🚀 Deploying configuration for $environment environment"
    
    # Validate environment
    if ! validate_environment "$environment"; then
        return 1
    fi
    
    # Determine source and target paths
    if [[ -n "$source_config" ]]; then
        if [[ ! -f "$source_config" ]]; then
            error "Source configuration not found: $source_config"
            return 1
        fi
        source_path="$source_config"
    else
        source_path="$CONFIG_DIR/sync-config-$environment.yaml"
        if [[ ! -f "$source_path" ]]; then
            error "Environment configuration not found: $source_path"
            error "Create it first with: $0 create $environment"
            return 1
        fi
    fi
    
    target_path="$CONFIG_DIR/sync-config.yaml"
    
    # Backup current configuration
    if [[ "$backup_flag" != "no-backup" && -f "$target_path" ]]; then
        log "💾 Backing up current configuration"
        backup_current_config
    fi
    
    # Validate configuration
    if [[ "$validate_flag" != "no-validate" ]]; then
        log "🔍 Validating configuration"
        if ! python3 "$SCRIPT_DIR/deploy_config.py" validate; then
            error "Configuration validation failed"
            return 1
        fi
    fi
    
    # Confirm deployment in production
    if [[ "$environment" == "production" && "$force_flag" != "force" ]]; then
        warning "You are about to deploy to PRODUCTION environment"
        read -p "Are you sure? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "❌ Deployment cancelled"
            return 1
        fi
    fi
    
    # Deploy configuration
    if cp "$source_path" "$target_path"; then
        success "Configuration deployed: $source_path → $target_path"
        
        # Update environment variable
        update_environment_file "$environment"
        
        # Show deployment summary
        show_deployment_summary "$environment" "$target_path"
        
        return 0
    else
        error "Failed to deploy configuration"
        return 1
    fi
}

# Create environment configuration
create_config() {
    local environment="$1"
    local base_config="$2"
    local force_flag="$3"
    
    log "📝 Creating configuration for $environment environment"
    
    # Validate environment
    if ! validate_environment "$environment"; then
        return 1
    fi
    
    target_path="$CONFIG_DIR/sync-config-$environment.yaml"
    
    # Check if configuration already exists
    if [[ -f "$target_path" && "$force_flag" != "force" ]]; then
        warning "Configuration already exists: $target_path"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "❌ Operation cancelled"
            return 1
        fi
    fi
    
    # Use Python script to create configuration
    if python3 "$SCRIPT_DIR/deploy_config.py" create "$environment" ${base_config:+--base "$base_config"}; then
        success "Environment configuration created: $target_path"
        return 0
    else
        error "Failed to create configuration"
        return 1
    fi
}

# Validate configurations
validate_configs() {
    log "🔍 Validating all configuration files"
    
    if python3 "$SCRIPT_DIR/deploy_config.py" validate; then
        success "All configurations are valid"
        return 0
    else
        error "Some configurations have validation errors"
        return 1
    fi
}

# List configurations
list_configs() {
    log "📋 Available configurations"
    python3 "$SCRIPT_DIR/deploy_config.py" list
}

# Compare configurations
compare_configs() {
    local config1="$1"
    local config2="$2"
    
    if [[ -z "$config1" || -z "$config2" ]]; then
        error "Both configuration files must be specified"
        return 1
    fi
    
    log "🔍 Comparing configurations"
    python3 "$SCRIPT_DIR/deploy_config.py" compare "$config1" "$config2"
}

# Backup current configuration
backup_current_config() {
    local current_config="$CONFIG_DIR/sync-config.yaml"
    
    if [[ ! -f "$current_config" ]]; then
        warning "No current configuration to backup"
        return 0
    fi
    
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local backup_name="sync-config_backup_$timestamp.yaml"
    local backup_path="$BACKUP_DIR/$backup_name"
    
    if cp "$current_config" "$backup_path"; then
        success "Configuration backed up: $backup_path"
        return 0
    else
        error "Failed to backup configuration"
        return 1
    fi
}

# Restore from backup
restore_config() {
    local backup_file="$1"
    local force_flag="$2"
    
    if [[ -z "$backup_file" ]]; then
        error "Backup file must be specified"
        return 1
    fi
    
    # Check if backup file exists
    if [[ -f "$backup_file" ]]; then
        backup_path="$backup_file"
    elif [[ -f "$BACKUP_DIR/$backup_file" ]]; then
        backup_path="$BACKUP_DIR/$backup_file"
    else
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "🔄 Restoring configuration from backup: $backup_path"
    
    # Confirm restore
    if [[ "$force_flag" != "force" ]]; then
        warning "This will overwrite the current configuration"
        read -p "Are you sure? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "❌ Restore cancelled"
            return 1
        fi
    fi
    
    # Backup current config before restore
    backup_current_config
    
    # Restore configuration
    target_path="$CONFIG_DIR/sync-config.yaml"
    if cp "$backup_path" "$target_path"; then
        success "Configuration restored from: $backup_path"
        return 0
    else
        error "Failed to restore configuration"
        return 1
    fi
}

# Update environment file
update_environment_file() {
    local environment="$1"
    local env_file="$PROJECT_ROOT/.env"
    
    # Create or update .env file
    {
        echo "# Environment configuration"
        echo "# Updated: $(date -Iseconds)"
        echo ""
        echo "SYNC_ENVIRONMENT=$environment"
        
        # Preserve other environment variables if they exist
        if [[ -f "$env_file" ]]; then
            grep -v "^SYNC_ENVIRONMENT=" "$env_file" | grep -v "^#" | grep -v "^$" || true
        fi
    } > "$env_file.tmp"
    
    mv "$env_file.tmp" "$env_file"
    log "📝 Environment file updated: SYNC_ENVIRONMENT=$environment"
}

# Show deployment summary
show_deployment_summary() {
    local environment="$1"
    local config_path="$2"
    
    log "📊 Deployment Summary"
    echo "   Environment: $environment"
    echo "   Config File: $config_path"
    echo "   Timestamp: $(date -Iseconds)"
    
    # Extract key settings from config
    if command -v yq >/dev/null 2>&1; then
        echo "   Sync Mode: $(yq eval '.sync_behavior.mode' "$config_path" 2>/dev/null || echo "unknown")"
        echo "   Max Concurrency: $(yq eval '.rate_limiting.max_concurrent_requests' "$config_path" 2>/dev/null || echo "unknown")"
        echo "   Debug Mode: $(yq eval '.debug_mode' "$config_path" 2>/dev/null || echo "unknown")"
    fi
    
    echo ""
    success "🎉 Configuration deployment completed successfully!"
    
    if [[ "$environment" == "production" ]]; then
        log "🚀 Production deployment complete. Monitor the next sync run carefully."
    fi
}

# Main script logic
main() {
    local command="$1"
    shift || true
    
    case "$command" in
        deploy)
            local environment="$1"
            local source_config=""
            local validate_flag="validate"
            local backup_flag="backup"
            local force_flag=""
            
            shift || true
            
            # Parse options
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --source)
                        source_config="$2"
                        shift 2
                        ;;
                    --no-validate)
                        validate_flag="no-validate"
                        shift
                        ;;
                    --no-backup)
                        backup_flag="no-backup"
                        shift
                        ;;
                    --force)
                        force_flag="force"
                        shift
                        ;;
                    *)
                        error "Unknown option: $1"
                        return 1
                        ;;
                esac
            done
            
            if [[ -z "$environment" ]]; then
                error "Environment must be specified"
                return 1
            fi
            
            deploy_config "$environment" "$source_config" "$validate_flag" "$backup_flag" "$force_flag"
            ;;
            
        create)
            local environment="$1"
            local base_config=""
            local force_flag=""
            
            shift || true
            
            # Parse options
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --base)
                        base_config="$2"
                        shift 2
                        ;;
                    --force)
                        force_flag="force"
                        shift
                        ;;
                    *)
                        error "Unknown option: $1"
                        return 1
                        ;;
                esac
            done
            
            if [[ -z "$environment" ]]; then
                error "Environment must be specified"
                return 1
            fi
            
            create_config "$environment" "$base_config" "$force_flag"
            ;;
            
        validate)
            validate_configs
            ;;
            
        list)
            list_configs
            ;;
            
        compare)
            local config1="$1"
            local config2="$2"
            compare_configs "$config1" "$config2"
            ;;
            
        backup)
            backup_current_config
            ;;
            
        restore)
            local backup_file="$1"
            local force_flag=""
            
            shift || true
            
            # Parse options
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --force)
                        force_flag="force"
                        shift
                        ;;
                    *)
                        error "Unknown option: $1"
                        return 1
                        ;;
                esac
            done
            
            restore_config "$backup_file" "$force_flag"
            ;;
            
        help|--help|-h)
            show_help
            ;;
            
        "")
            error "No command specified"
            show_help
            return 1
            ;;
            
        *)
            error "Unknown command: $command"
            show_help
            return 1
            ;;
    esac
}

# Check dependencies
check_dependencies() {
    if ! command -v python3 >/dev/null 2>&1; then
        error "Python 3 is required but not installed"
        return 1
    fi
    
    # Check if required Python modules are available
    if ! python3 -c "import yaml" 2>/dev/null; then
        warning "PyYAML not found. Install with: pip install PyYAML"
    fi
}

# Run dependency check
check_dependencies

# Run main function with all arguments
main "$@"