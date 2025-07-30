@echo off
REM Configuration Deployment Script for Windows
REM Provides easy deployment and management of sync configurations

setlocal enabledelayedexpansion

REM Script directory
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%\.."

REM Configuration directories
set "CONFIG_DIR=%PROJECT_ROOT%\config"
set "BACKUP_DIR=%CONFIG_DIR%\backups"

REM Ensure directories exist
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

REM Colors (if supported)
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

REM Main script logic
if "%1"=="" goto :show_help
if "%1"=="help" goto :show_help
if "%1"=="--help" goto :show_help
if "%1"=="-h" goto :show_help

if "%1"=="deploy" goto :deploy_config
if "%1"=="create" goto :create_config
if "%1"=="validate" goto :validate_configs
if "%1"=="list" goto :list_configs
if "%1"=="compare" goto :compare_configs
if "%1"=="backup" goto :backup_config
if "%1"=="restore" goto :restore_config

echo %RED%[ERROR]%NC% Unknown command: %1
goto :show_help

:show_help
echo Configuration Deployment Script
echo.
echo Usage: %0 [COMMAND] [OPTIONS]
echo.
echo Commands:
echo     deploy ^<environment^>     Deploy configuration for environment
echo     create ^<environment^>     Create new environment configuration
echo     validate                 Validate all configurations
echo     list                     List available configurations
echo     compare ^<config1^> ^<config2^>  Compare two configurations
echo     backup                   Backup current configuration
echo     restore ^<backup_file^>    Restore from backup
echo     help                     Show this help message
echo.
echo Environments:
echo     development             Development environment
echo     staging                 Staging environment  
echo     production              Production environment
echo.
echo Examples:
echo     %0 deploy production
echo     %0 create development
echo     %0 validate
echo     %0 list
echo     %0 backup
goto :end

:deploy_config
if "%2"=="" (
    echo %RED%[ERROR]%NC% Environment must be specified
    goto :end
)

set "ENVIRONMENT=%2"
call :validate_environment "%ENVIRONMENT%"
if errorlevel 1 goto :end

echo %BLUE%[INFO]%NC% Deploying configuration for %ENVIRONMENT% environment

REM Determine source and target paths
set "SOURCE_PATH=%CONFIG_DIR%\sync-config-%ENVIRONMENT%.yaml"
set "TARGET_PATH=%CONFIG_DIR%\sync-config.yaml"

if not exist "%SOURCE_PATH%" (
    echo %RED%[ERROR]%NC% Environment configuration not found: %SOURCE_PATH%
    echo %RED%[ERROR]%NC% Create it first with: %0 create %ENVIRONMENT%
    goto :end
)

REM Backup current configuration
if exist "%TARGET_PATH%" (
    echo %BLUE%[INFO]%NC% Backing up current configuration
    call :backup_current_config
)

REM Validate configuration
echo %BLUE%[INFO]%NC% Validating configuration
python "%SCRIPT_DIR%\deploy_config.py" validate
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Configuration validation failed
    goto :end
)

REM Confirm deployment in production
if "%ENVIRONMENT%"=="production" (
    echo %YELLOW%[WARNING]%NC% You are about to deploy to PRODUCTION environment
    set /p "CONFIRM=Are you sure? (y/N): "
    if /i not "!CONFIRM!"=="y" (
        echo %BLUE%[INFO]%NC% Deployment cancelled
        goto :end
    )
)

REM Deploy configuration
copy "%SOURCE_PATH%" "%TARGET_PATH%" >nul
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Failed to deploy configuration
    goto :end
)

echo %GREEN%[SUCCESS]%NC% Configuration deployed: %SOURCE_PATH% -^> %TARGET_PATH%

REM Update environment variable
call :update_environment_file "%ENVIRONMENT%"

echo %GREEN%[SUCCESS]%NC% Configuration deployment completed successfully!
goto :end

:create_config
if "%2"=="" (
    echo %RED%[ERROR]%NC% Environment must be specified
    goto :end
)

set "ENVIRONMENT=%2"
call :validate_environment "%ENVIRONMENT%"
if errorlevel 1 goto :end

echo %BLUE%[INFO]%NC% Creating configuration for %ENVIRONMENT% environment

set "TARGET_PATH=%CONFIG_DIR%\sync-config-%ENVIRONMENT%.yaml"

if exist "%TARGET_PATH%" (
    echo %YELLOW%[WARNING]%NC% Configuration already exists: %TARGET_PATH%
    set /p "CONFIRM=Overwrite? (y/N): "
    if /i not "!CONFIRM!"=="y" (
        echo %BLUE%[INFO]%NC% Operation cancelled
        goto :end
    )
)

python "%SCRIPT_DIR%\deploy_config.py" create "%ENVIRONMENT%"
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Failed to create configuration
    goto :end
)

echo %GREEN%[SUCCESS]%NC% Environment configuration created: %TARGET_PATH%
goto :end

:validate_configs
echo %BLUE%[INFO]%NC% Validating all configuration files
python "%SCRIPT_DIR%\deploy_config.py" validate
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Some configurations have validation errors
    goto :end
)
echo %GREEN%[SUCCESS]%NC% All configurations are valid
goto :end

:list_configs
echo %BLUE%[INFO]%NC% Available configurations
python "%SCRIPT_DIR%\deploy_config.py" list
goto :end

:compare_configs
if "%2"=="" (
    echo %RED%[ERROR]%NC% First configuration file must be specified
    goto :end
)
if "%3"=="" (
    echo %RED%[ERROR]%NC% Second configuration file must be specified
    goto :end
)

echo %BLUE%[INFO]%NC% Comparing configurations
python "%SCRIPT_DIR%\deploy_config.py" compare "%2" "%3"
goto :end

:backup_config
call :backup_current_config
goto :end

:restore_config
if "%2"=="" (
    echo %RED%[ERROR]%NC% Backup file must be specified
    goto :end
)

set "BACKUP_FILE=%2"
if exist "%BACKUP_FILE%" (
    set "BACKUP_PATH=%BACKUP_FILE%"
) else if exist "%BACKUP_DIR%\%BACKUP_FILE%" (
    set "BACKUP_PATH=%BACKUP_DIR%\%BACKUP_FILE%"
) else (
    echo %RED%[ERROR]%NC% Backup file not found: %BACKUP_FILE%
    goto :end
)

echo %BLUE%[INFO]%NC% Restoring configuration from backup: !BACKUP_PATH!

echo %YELLOW%[WARNING]%NC% This will overwrite the current configuration
set /p "CONFIRM=Are you sure? (y/N): "
if /i not "!CONFIRM!"=="y" (
    echo %BLUE%[INFO]%NC% Restore cancelled
    goto :end
)

REM Backup current config before restore
call :backup_current_config

REM Restore configuration
set "TARGET_PATH=%CONFIG_DIR%\sync-config.yaml"
copy "!BACKUP_PATH!" "%TARGET_PATH%" >nul
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Failed to restore configuration
    goto :end
)

echo %GREEN%[SUCCESS]%NC% Configuration restored from: !BACKUP_PATH!
goto :end

:validate_environment
set "ENV=%~1"
if "%ENV%"=="development" goto :valid_env
if "%ENV%"=="staging" goto :valid_env
if "%ENV%"=="production" goto :valid_env
if "%ENV%"=="testing" goto :valid_env

echo %RED%[ERROR]%NC% Invalid environment: %ENV%
echo %RED%[ERROR]%NC% Valid environments: development, staging, production, testing
exit /b 1

:valid_env
exit /b 0

:backup_current_config
set "CURRENT_CONFIG=%CONFIG_DIR%\sync-config.yaml"

if not exist "%CURRENT_CONFIG%" (
    echo %YELLOW%[WARNING]%NC% No current configuration to backup
    exit /b 0
)

REM Generate timestamp
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "TIMESTAMP=%dt:~0,8%_%dt:~8,6%"

set "BACKUP_NAME=sync-config_backup_%TIMESTAMP%.yaml"
set "BACKUP_PATH=%BACKUP_DIR%\%BACKUP_NAME%"

copy "%CURRENT_CONFIG%" "%BACKUP_PATH%" >nul
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Failed to backup configuration
    exit /b 1
)

echo %GREEN%[SUCCESS]%NC% Configuration backed up: %BACKUP_PATH%
exit /b 0

:update_environment_file
set "ENVIRONMENT=%~1"
set "ENV_FILE=%PROJECT_ROOT%\.env"

REM Create or update .env file
(
    echo # Environment configuration
    echo # Updated: %date% %time%
    echo.
    echo SYNC_ENVIRONMENT=%ENVIRONMENT%
) > "%ENV_FILE%"

echo %BLUE%[INFO]%NC% Environment file updated: SYNC_ENVIRONMENT=%ENVIRONMENT%
exit /b 0

:end
endlocal