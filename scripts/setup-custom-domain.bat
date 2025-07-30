@echo off
REM GGUF Model Index - Custom Domain Setup Script (Windows)
REM ========================================================
REM This script helps configure a custom domain for GitHub Pages

echo.
echo 🌐 Custom Domain Setup for GitHub Pages
echo =======================================
echo.

REM Get domain from user
set /p "DOMAIN=Enter your custom domain (e.g., models.yourdomain.com): "

if "%DOMAIN%"=="" (
    echo ❌ Domain is required
    pause
    exit /b 1
)

REM Create CNAME file
echo %DOMAIN%> CNAME
echo ✅ Created CNAME file with domain: %DOMAIN%

REM Determine domain type and provide DNS instructions
echo.
echo ℹ️  DNS Configuration Instructions
echo ==============================
echo.

REM Simple check for apex domain (no subdomain)
echo %DOMAIN% | find "." >nul
if %errorlevel% equ 0 (
    REM Count dots to determine if it's apex or subdomain
    for /f "delims=. tokens=1,2,3" %%a in ("%DOMAIN%") do (
        if "%%c"=="" (
            REM Apex domain
            echo For apex domain ^(%DOMAIN%^), create these A records:
            echo   185.199.108.153
            echo   185.199.109.153
            echo   185.199.110.153
            echo   185.199.111.153
            echo.
            echo Also create a CNAME record for www subdomain:
            for /f "tokens=*" %%i in ('git config --get remote.origin.url') do (
                echo   www.%DOMAIN% -^> %%i
            )
        ) else (
            REM Subdomain
            echo For subdomain ^(%DOMAIN%^), create this CNAME record:
            for /f "tokens=*" %%i in ('git config --get remote.origin.url') do (
                echo   %DOMAIN% -^> %%i
            )
        )
    )
)

echo.
echo ℹ️  GitHub Repository Configuration
echo ===============================
echo.
echo After configuring DNS:
echo 1. Go to your repository Settings ^> Pages
echo 2. Enter '%DOMAIN%' in the Custom domain field
echo 3. Enable 'Enforce HTTPS' ^(recommended^)
echo 4. Wait for DNS verification ^(may take up to 24 hours^)

REM Commit CNAME file
echo.
echo ℹ️  Committing CNAME file...

git add CNAME
git commit -m "Add custom domain: %DOMAIN%"
git push

echo ✅ CNAME file committed and pushed

echo.
echo ✅ Custom domain setup complete!
echo.
echo ℹ️  Next steps:
echo 1. Configure DNS as shown above
echo 2. Update GitHub Pages settings
echo 3. Wait for DNS propagation
echo 4. Test your custom domain
echo.
pause