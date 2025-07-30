#!/bin/bash

# Deployment Monitoring Script
# Monitors GitHub Pages deployment and data pipeline health

set -e

# Configuration
SITE_URL="https://your-username.github.io/gguf-model-discovery"
GITHUB_API="https://api.github.com/repos/your-username/gguf-model-discovery"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
EMAIL_RECIPIENT="${EMAIL_RECIPIENT:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check if site is accessible
check_site_accessibility() {
    log "Checking site accessibility..."
    
    local response_code
    response_code=$(curl -s -o /dev/null -w "%{http_code}" "$SITE_URL" || echo "000")
    
    if [ "$response_code" = "200" ]; then
        success "Site is accessible (HTTP $response_code)"
        return 0
    else
        error "Site is not accessible (HTTP $response_code)"
        return 1
    fi
}

# Check data freshness
check_data_freshness() {
    log "Checking data freshness..."
    
    local data_url="${SITE_URL}/gguf_models.json"
    local temp_file="/tmp/gguf_models.json"
    
    if curl -s "$data_url" -o "$temp_file"; then
        local last_updated
        last_updated=$(python3 -c "
import json
import sys
from datetime import datetime, timezone

try:
    with open('$temp_file', 'r') as f:
        data = json.load(f)
    
    last_updated = data.get('metadata', {}).get('lastUpdated', '')
    if last_updated:
        # Parse ISO format date
        dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
        hours_ago = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        print(f'{hours_ago:.1f}')
    else:
        print('999')
except Exception as e:
    print('999')
        ")
        
        if (( $(echo "$last_updated < 25" | bc -l) )); then
            success "Data is fresh (updated ${last_updated} hours ago)"
            return 0
        else
            warning "Data is stale (updated ${last_updated} hours ago)"
            return 1
        fi
    else
        error "Could not fetch data file"
        return 1
    fi
}

# Check GitHub Actions status
check_github_actions() {
    log "Checking GitHub Actions status..."
    
    if [ -z "$GITHUB_TOKEN" ]; then
        warning "GITHUB_TOKEN not set, skipping GitHub Actions check"
        return 0
    fi
    
    local workflow_runs
    workflow_runs=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
        "$GITHUB_API/actions/runs?per_page=5" | \
        python3 -c "
import json
import sys

try:
    data = json.load(sys.stdin)
    runs = data.get('workflow_runs', [])
    
    for run in runs[:3]:  # Check last 3 runs
        name = run.get('name', 'Unknown')
        status = run.get('status', 'unknown')
        conclusion = run.get('conclusion', 'unknown')
        created_at = run.get('created_at', '')
        
        print(f'{name}|{status}|{conclusion}|{created_at}')
except Exception as e:
    print('ERROR|unknown|unknown|')
        ")
    
    local failed_count=0
    while IFS='|' read -r name status conclusion created_at; do
        if [ "$name" = "ERROR" ]; then
            error "Could not fetch GitHub Actions status"
            return 1
        fi
        
        if [ "$conclusion" = "failure" ]; then
            error "Workflow '$name' failed (status: $status)"
            ((failed_count++))
        elif [ "$conclusion" = "success" ]; then
            success "Workflow '$name' succeeded"
        else
            log "Workflow '$name' is $status"
        fi
    done <<< "$workflow_runs"
    
    if [ $failed_count -gt 0 ]; then
        return 1
    else
        return 0
    fi
}

# Check site performance
check_performance() {
    log "Checking site performance..."
    
    local load_time
    load_time=$(curl -s -w "%{time_total}" -o /dev/null "$SITE_URL")
    
    if (( $(echo "$load_time < 3.0" | bc -l) )); then
        success "Site loads quickly (${load_time}s)"
        return 0
    elif (( $(echo "$load_time < 5.0" | bc -l) )); then
        warning "Site loads slowly (${load_time}s)"
        return 0
    else
        error "Site loads very slowly (${load_time}s)"
        return 1
    fi
}

# Check SSL certificate
check_ssl_certificate() {
    log "Checking SSL certificate..."
    
    local domain
    domain=$(echo "$SITE_URL" | sed 's|https\?://||' | sed 's|/.*||')
    
    local cert_info
    cert_info=$(echo | openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null | \
        openssl x509 -noout -dates 2>/dev/null || echo "ERROR")
    
    if [ "$cert_info" = "ERROR" ]; then
        error "Could not check SSL certificate"
        return 1
    fi
    
    local expiry_date
    expiry_date=$(echo "$cert_info" | grep "notAfter" | cut -d= -f2)
    
    local days_until_expiry
    days_until_expiry=$(python3 -c "
from datetime import datetime
import sys

try:
    expiry = datetime.strptime('$expiry_date', '%b %d %H:%M:%S %Y %Z')
    now = datetime.now()
    days = (expiry - now).days
    print(days)
except:
    print(-1)
    ")
    
    if [ "$days_until_expiry" -gt 30 ]; then
        success "SSL certificate is valid ($days_until_expiry days remaining)"
        return 0
    elif [ "$days_until_expiry" -gt 7 ]; then
        warning "SSL certificate expires soon ($days_until_expiry days remaining)"
        return 0
    else
        error "SSL certificate expires very soon ($days_until_expiry days remaining)"
        return 1
    fi
}

# Send notification
send_notification() {
    local status="$1"
    local message="$2"
    
    # Slack notification
    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        local color
        case "$status" in
            "success") color="good" ;;
            "warning") color="warning" ;;
            "error") color="danger" ;;
            *) color="warning" ;;
        esac
        
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"attachments\":[{\"color\":\"$color\",\"title\":\"GGUF Model Discovery - Monitoring Alert\",\"text\":\"$message\"}]}" \
            "$SLACK_WEBHOOK_URL" > /dev/null
    fi
    
    # Email notification (requires mailutils)
    if [ -n "$EMAIL_RECIPIENT" ] && command -v mail >/dev/null 2>&1; then
        echo "$message" | mail -s "GGUF Model Discovery - Monitoring Alert" "$EMAIL_RECIPIENT"
    fi
}

# Main monitoring function
run_monitoring() {
    log "Starting deployment monitoring..."
    
    local overall_status="success"
    local issues=()
    
    # Run all checks
    if ! check_site_accessibility; then
        overall_status="error"
        issues+=("Site is not accessible")
    fi
    
    if ! check_data_freshness; then
        if [ "$overall_status" != "error" ]; then
            overall_status="warning"
        fi
        issues+=("Data is stale")
    fi
    
    if ! check_github_actions; then
        overall_status="error"
        issues+=("GitHub Actions failures detected")
    fi
    
    if ! check_performance; then
        if [ "$overall_status" != "error" ]; then
            overall_status="warning"
        fi
        issues+=("Performance issues detected")
    fi
    
    if ! check_ssl_certificate; then
        if [ "$overall_status" != "error" ]; then
            overall_status="warning"
        fi
        issues+=("SSL certificate issues")
    fi
    
    # Generate summary
    local summary
    if [ "$overall_status" = "success" ]; then
        summary="✅ All systems operational"
        success "$summary"
    elif [ "$overall_status" = "warning" ]; then
        summary="⚠️ Issues detected: $(IFS=', '; echo "${issues[*]}")"
        warning "$summary"
    else
        summary="🚨 Critical issues: $(IFS=', '; echo "${issues[*]}")"
        error "$summary"
    fi
    
    # Send notification if there are issues
    if [ "$overall_status" != "success" ]; then
        send_notification "$overall_status" "$summary"
    fi
    
    log "Monitoring complete"
    
    # Exit with appropriate code
    case "$overall_status" in
        "success") exit 0 ;;
        "warning") exit 1 ;;
        "error") exit 2 ;;
    esac
}

# Health check endpoint
health_check() {
    local checks=0
    local passed=0
    
    echo "{"
    echo "  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    echo "  \"checks\": {"
    
    # Site accessibility
    echo -n "    \"site_accessible\": "
    if check_site_accessibility >/dev/null 2>&1; then
        echo "true,"
        ((passed++))
    else
        echo "false,"
    fi
    ((checks++))
    
    # Data freshness
    echo -n "    \"data_fresh\": "
    if check_data_freshness >/dev/null 2>&1; then
        echo "true,"
        ((passed++))
    else
        echo "false,"
    fi
    ((checks++))
    
    # Performance
    echo -n "    \"performance_ok\": "
    if check_performance >/dev/null 2>&1; then
        echo "true"
        ((passed++))
    else
        echo "false"
    fi
    ((checks++))
    
    echo "  },"
    echo "  \"summary\": {"
    echo "    \"total_checks\": $checks,"
    echo "    \"passed_checks\": $passed,"
    echo "    \"health_score\": $(echo "scale=2; $passed * 100 / $checks" | bc)"
    echo "  }"
    echo "}"
}

# Command line interface
case "${1:-monitor}" in
    "monitor")
        run_monitoring
        ;;
    "health")
        health_check
        ;;
    "accessibility")
        check_site_accessibility
        ;;
    "data")
        check_data_freshness
        ;;
    "actions")
        check_github_actions
        ;;
    "performance")
        check_performance
        ;;
    "ssl")
        check_ssl_certificate
        ;;
    *)
        echo "Usage: $0 [monitor|health|accessibility|data|actions|performance|ssl]"
        echo ""
        echo "Commands:"
        echo "  monitor       - Run all monitoring checks (default)"
        echo "  health        - Output health status as JSON"
        echo "  accessibility - Check if site is accessible"
        echo "  data          - Check data freshness"
        echo "  actions       - Check GitHub Actions status"
        echo "  performance   - Check site performance"
        echo "  ssl           - Check SSL certificate"
        exit 1
        ;;
esac