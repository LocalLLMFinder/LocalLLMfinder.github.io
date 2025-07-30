#!/usr/bin/env python3
"""
Configuration Deployment Script

This script provides easy deployment and management of configuration files
across different environments with validation and backup capabilities.
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging

# Import our configuration system
from config_system import (
    ConfigurationManager, SyncConfiguration, Environment,
    create_default_configuration
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ConfigurationDeployer:
    """Handles deployment and management of configuration files."""
    
    def __init__(self):
        self.config_dir = Path("config")
        self.backup_dir = Path("config/backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def deploy_configuration(self, environment: str, source_config: Optional[str] = None, 
                           validate: bool = True, backup: bool = True) -> bool:
        """Deploy configuration for a specific environment."""
        logger.info(f"🚀 Deploying configuration for {environment} environment")
        
        try:
            env_enum = Environment(environment.lower())
        except ValueError:
            logger.error(f"❌ Invalid environment: {environment}")
            logger.info(f"Valid environments: {[e.value for e in Environment]}")
            return False
        
        # Determine source and target paths
        if source_config:
            source_path = Path(source_config)
        else:
            source_path = self.config_dir / f"sync-config-{environment}.yaml"
        
        target_path = self.config_dir / "sync-config.yaml"
        
        # Validate source exists
        if not source_path.exists():
            logger.error(f"❌ Source configuration not found: {source_path}")
            return False
        
        # Backup current configuration
        if backup and target_path.exists():
            if not self._backup_configuration(target_path):
                logger.warning("⚠️ Failed to backup current configuration")
        
        # Validate configuration before deployment
        if validate:
            if not self._validate_configuration_file(source_path, env_enum):
                logger.error("❌ Configuration validation failed")
                return False
        
        # Deploy configuration
        try:
            shutil.copy2(source_path, target_path)
            logger.info(f"✅ Configuration deployed: {source_path} → {target_path}")
            
            # Set environment variable for the deployment
            self._update_environment_file(environment)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to deploy configuration: {e}")
            return False
    
    def create_environment_config(self, environment: str, base_config: Optional[str] = None) -> bool:
        """Create a new environment-specific configuration."""
        logger.info(f"📝 Creating configuration for {environment} environment")
        
        try:
            env_enum = Environment(environment.lower())
        except ValueError:
            logger.error(f"❌ Invalid environment: {environment}")
            return False
        
        target_path = self.config_dir / f"sync-config-{environment}.yaml"
        
        if target_path.exists():
            logger.warning(f"⚠️ Configuration already exists: {target_path}")
            response = input("Overwrite? (y/N): ").strip().lower()
            if response != 'y':
                logger.info("❌ Operation cancelled")
                return False
        
        # Load base configuration
        if base_config:
            base_path = Path(base_config)
            if not base_path.exists():
                logger.error(f"❌ Base configuration not found: {base_path}")
                return False
            
            manager = ConfigurationManager(str(base_path))
            config = manager.load_configuration()
        else:
            config = create_default_configuration()
        
        # Apply environment-specific settings
        config.environment = env_enum
        
        # Save configuration
        manager = ConfigurationManager(str(target_path))
        manager.config = config
        
        if manager.save_configuration():
            logger.info(f"✅ Environment configuration created: {target_path}")
            return True
        else:
            logger.error("❌ Failed to save configuration")
            return False
    
    def validate_all_configurations(self) -> bool:
        """Validate all configuration files."""
        logger.info("🔍 Validating all configuration files")
        
        config_files = list(self.config_dir.glob("sync-config*.yaml"))
        if not config_files:
            logger.warning("⚠️ No configuration files found")
            return True
        
        all_valid = True
        
        for config_file in config_files:
            logger.info(f"📋 Validating {config_file.name}")
            
            try:
                manager = ConfigurationManager(str(config_file))
                config = manager.load_configuration()
                
                if manager.validate_configuration():
                    logger.info(f"✅ {config_file.name} is valid")
                else:
                    logger.error(f"❌ {config_file.name} validation failed")
                    for error in manager._validation_errors:
                        logger.error(f"   • {error}")
                    all_valid = False
                    
            except Exception as e:
                logger.error(f"❌ Failed to validate {config_file.name}: {e}")
                all_valid = False
        
        if all_valid:
            logger.info("✅ All configurations are valid")
        else:
            logger.error("❌ Some configurations have validation errors")
        
        return all_valid
    
    def list_configurations(self) -> None:
        """List all available configurations."""
        logger.info("📋 Available configurations:")
        
        config_files = list(self.config_dir.glob("sync-config*.yaml"))
        
        if not config_files:
            logger.info("   No configuration files found")
            return
        
        for config_file in sorted(config_files):
            try:
                manager = ConfigurationManager(str(config_file))
                config = manager.load_configuration()
                
                # Extract environment from filename or config
                if config_file.name == "sync-config.yaml":
                    env_name = "current"
                else:
                    env_name = config_file.stem.replace("sync-config-", "")
                
                logger.info(f"   📄 {config_file.name}")
                logger.info(f"      Environment: {config.environment.value if hasattr(config.environment, 'value') else config.environment}")
                logger.info(f"      Sync Mode: {config.sync_behavior.mode.value if hasattr(config.sync_behavior.mode, 'value') else config.sync_behavior.mode}")
                logger.info(f"      Max Concurrency: {config.rate_limiting.max_concurrent_requests}")
                logger.info(f"      Debug Mode: {config.debug_mode}")
                logger.info("")
                
            except Exception as e:
                logger.error(f"   ❌ {config_file.name}: Error loading ({e})")
    
    def compare_configurations(self, config1: str, config2: str) -> None:
        """Compare two configuration files."""
        logger.info(f"🔍 Comparing {config1} vs {config2}")
        
        path1 = self.config_dir / config1 if not config1.startswith('/') else Path(config1)
        path2 = self.config_dir / config2 if not config2.startswith('/') else Path(config2)
        
        if not path1.exists():
            logger.error(f"❌ Configuration not found: {path1}")
            return
        
        if not path2.exists():
            logger.error(f"❌ Configuration not found: {path2}")
            return
        
        try:
            manager1 = ConfigurationManager(str(path1))
            config1_obj = manager1.load_configuration()
            
            manager2 = ConfigurationManager(str(path2))
            config2_obj = manager2.load_configuration()
            
            # Compare key settings
            comparisons = [
                ("Environment", config1_obj.environment.value, config2_obj.environment.value),
                ("Sync Mode", config1_obj.sync_behavior.mode.value, config2_obj.sync_behavior.mode.value),
                ("Debug Mode", config1_obj.debug_mode, config2_obj.debug_mode),
                ("Max Concurrency", config1_obj.rate_limiting.max_concurrent_requests, config2_obj.rate_limiting.max_concurrent_requests),
                ("Requests/sec", config1_obj.rate_limiting.requests_per_second, config2_obj.rate_limiting.requests_per_second),
                ("Incremental Window", f"{config1_obj.sync_behavior.incremental_window_hours}h", f"{config2_obj.sync_behavior.incremental_window_hours}h"),
                ("Full Sync Threshold", f"{config1_obj.sync_behavior.full_sync_threshold_hours}h", f"{config2_obj.sync_behavior.full_sync_threshold_hours}h"),
                ("Min Completeness", config1_obj.validation.min_completeness_score, config2_obj.validation.min_completeness_score),
                ("Progress Interval", f"{config1_obj.monitoring.progress_report_interval_seconds}s", f"{config2_obj.monitoring.progress_report_interval_seconds}s"),
            ]
            
            logger.info("📊 Configuration Comparison:")
            logger.info(f"{'Setting':<20} {'Config 1':<15} {'Config 2':<15} {'Match':<8}")
            logger.info("-" * 65)
            
            for setting, val1, val2 in comparisons:
                match = "✅" if val1 == val2 else "❌"
                logger.info(f"{setting:<20} {str(val1):<15} {str(val2):<15} {match:<8}")
            
        except Exception as e:
            logger.error(f"❌ Failed to compare configurations: {e}")
    
    def _backup_configuration(self, config_path: Path) -> bool:
        """Backup current configuration."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{config_path.stem}_backup_{timestamp}.yaml"
        backup_path = self.backup_dir / backup_name
        
        try:
            shutil.copy2(config_path, backup_path)
            logger.info(f"💾 Configuration backed up: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to backup configuration: {e}")
            return False
    
    def _validate_configuration_file(self, config_path: Path, expected_env: Environment) -> bool:
        """Validate a configuration file."""
        try:
            manager = ConfigurationManager(str(config_path))
            config = manager.load_configuration()
            
            # Check if environment matches expected
            if config.environment != expected_env:
                logger.warning(f"⚠️ Environment mismatch: expected {expected_env.value}, got {config.environment.value}")
            
            return manager.validate_configuration()
            
        except Exception as e:
            logger.error(f"❌ Validation failed: {e}")
            return False
    
    def _update_environment_file(self, environment: str) -> None:
        """Update .env file with current environment."""
        env_file = Path(".env")
        
        try:
            # Read existing .env file
            env_vars = {}
            if env_file.exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key] = value
            
            # Update environment
            env_vars['SYNC_ENVIRONMENT'] = environment
            
            # Write back to .env file
            with open(env_file, 'w') as f:
                f.write(f"# Environment configuration\n")
                f.write(f"# Updated: {datetime.now().isoformat()}\n\n")
                for key, value in env_vars.items():
                    f.write(f"{key}={value}\n")
            
            logger.info(f"📝 Environment file updated: SYNC_ENVIRONMENT={environment}")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to update .env file: {e}")

def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description="Configuration Deployment Tool")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Deploy command
    deploy_parser = subparsers.add_parser('deploy', help='Deploy configuration for environment')
    deploy_parser.add_argument('environment', help='Target environment (development, staging, production)')
    deploy_parser.add_argument('--source', help='Source configuration file')
    deploy_parser.add_argument('--no-validate', action='store_true', help='Skip validation')
    deploy_parser.add_argument('--no-backup', action='store_true', help='Skip backup')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create new environment configuration')
    create_parser.add_argument('environment', help='Environment name')
    create_parser.add_argument('--base', help='Base configuration file')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate configurations')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available configurations')
    
    # Compare command
    compare_parser = subparsers.add_parser('compare', help='Compare two configurations')
    compare_parser.add_argument('config1', help='First configuration file')
    compare_parser.add_argument('config2', help='Second configuration file')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    deployer = ConfigurationDeployer()
    
    try:
        if args.command == 'deploy':
            success = deployer.deploy_configuration(
                args.environment,
                args.source,
                validate=not args.no_validate,
                backup=not args.no_backup
            )
            sys.exit(0 if success else 1)
            
        elif args.command == 'create':
            success = deployer.create_environment_config(args.environment, args.base)
            sys.exit(0 if success else 1)
            
        elif args.command == 'validate':
            success = deployer.validate_all_configurations()
            sys.exit(0 if success else 1)
            
        elif args.command == 'list':
            deployer.list_configurations()
            
        elif args.command == 'compare':
            deployer.compare_configurations(args.config1, args.config2)
            
    except KeyboardInterrupt:
        logger.info("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()