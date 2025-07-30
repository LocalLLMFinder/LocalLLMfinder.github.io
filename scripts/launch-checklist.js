#!/usr/bin/env node

/**
 * Launch Checklist Script
 * Validates all systems are ready for production launch
 */

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

// Colors for console output
const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m'
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function success(message) {
  log(`✅ ${message}`, 'green');
}

function error(message) {
  log(`❌ ${message}`, 'red');
}

function warning(message) {
  log(`⚠️  ${message}`, 'yellow');
}

function info(message) {
  log(`ℹ️  ${message}`, 'blue');
}

function header(message) {
  log(`\n🚀 ${message}`, 'cyan');
  log('='.repeat(50), 'cyan');
}

class LaunchChecker {
  constructor() {
    this.checks = [];
    this.passed = 0;
    this.failed = 0;
    this.warnings = 0;
  }

  addCheck(name, fn, critical = true) {
    this.checks.push({ name, fn, critical });
  }

  async runCheck(check) {
    try {
      const result = await check.fn();
      if (result.status === 'pass') {
        success(`${check.name}: ${result.message}`);
        this.passed++;
        return true;
      } else if (result.status === 'warn') {
        warning(`${check.name}: ${result.message}`);
        this.warnings++;
        return !check.critical;
      } else {
        error(`${check.name}: ${result.message}`);
        this.failed++;
        return false;
      }
    } catch (err) {
      error(`${check.name}: ${err.message}`);
      this.failed++;
      return false;
    }
  }

  async runAll() {
    header('Pre-Launch Validation');
    
    let allPassed = true;
    
    for (const check of this.checks) {
      const passed = await this.runCheck(check);
      if (!passed && check.critical) {
        allPassed = false;
      }
    }
    
    this.printSummary();
    return allPassed;
  }

  printSummary() {
    header('Launch Readiness Summary');
    
    const total = this.passed + this.failed + this.warnings;
    const score = Math.round((this.passed / total) * 100);
    
    log(`Total Checks: ${total}`);
    success(`Passed: ${this.passed}`);
    if (this.warnings > 0) warning(`Warnings: ${this.warnings}`);
    if (this.failed > 0) error(`Failed: ${this.failed}`);
    
    log(`\nOverall Score: ${score}%`, score >= 90 ? 'green' : score >= 70 ? 'yellow' : 'red');
    
    if (score >= 90) {
      success('\n🎉 System is ready for launch!');
    } else if (score >= 70) {
      warning('\n⚠️  System has issues but may be launched with caution');
    } else {
      error('\n🚨 System is not ready for launch - fix critical issues first');
    }
  }
}

// Check functions
const checks = {
  async fileStructure() {
    const requiredFiles = [
      'index.html',
      'package.json',
      'vite.config.js',
      '.nojekyll',
      '404.html',
      'robots.txt',
      'sitemap.xml',
      'README.md',
      'DEPLOYMENT_GUIDE.md',
      'TROUBLESHOOTING.md'
    ];
    
    const missing = requiredFiles.filter(file => !fs.existsSync(file));
    
    if (missing.length === 0) {
      return { status: 'pass', message: 'All required files present' };
    } else {
      return { status: 'fail', message: `Missing files: ${missing.join(', ')}` };
    }
  },

  async dataFiles() {
    const dataFiles = ['gguf_models.json', 'gguf_models_estimated_sizes.json'];
    const missing = dataFiles.filter(file => !fs.existsSync(file));
    
    if (missing.length === 0) {
      // Check if data is recent
      const stats = fs.statSync('gguf_models.json');
      const ageHours = (Date.now() - stats.mtime.getTime()) / (1000 * 60 * 60);
      
      if (ageHours < 25) {
        return { status: 'pass', message: `Data files present and fresh (${ageHours.toFixed(1)}h old)` };
      } else {
        return { status: 'warn', message: `Data files present but stale (${ageHours.toFixed(1)}h old)` };
      }
    } else {
      return { status: 'fail', message: `Missing data files: ${missing.join(', ')}` };
    }
  },

  async githubWorkflows() {
    const workflows = [
      '.github/workflows/update-gguf-models.yml',
      '.github/workflows/deploy-pages.yml',
      '.github/workflows/deployment-notifications.yml'
    ];
    
    const missing = workflows.filter(file => !fs.existsSync(file));
    
    if (missing.length === 0) {
      return { status: 'pass', message: 'All GitHub workflows configured' };
    } else {
      return { status: 'fail', message: `Missing workflows: ${missing.join(', ')}` };
    }
  },

  async packageDependencies() {
    try {
      const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf8'));
      const requiredDeps = ['vite', 'tailwindcss'];
      const requiredDevDeps = ['vitest', 'terser'];
      
      const missingDeps = requiredDeps.filter(dep => !packageJson.dependencies?.[dep]);
      const missingDevDeps = requiredDevDeps.filter(dep => !packageJson.devDependencies?.[dep]);
      
      if (missingDeps.length === 0 && missingDevDeps.length === 0) {
        return { status: 'pass', message: 'All required dependencies present' };
      } else {
        const missing = [...missingDeps, ...missingDevDeps];
        return { status: 'fail', message: `Missing dependencies: ${missing.join(', ')}` };
      }
    } catch (err) {
      return { status: 'fail', message: 'Could not read package.json' };
    }
  },

  async buildProcess() {
    try {
      // Check if node_modules exists
      if (!fs.existsSync('node_modules')) {
        return { status: 'fail', message: 'Dependencies not installed - run npm install' };
      }
      
      // Try to build
      execSync('npm run build', { stdio: 'pipe' });
      
      // Check if build output exists
      if (fs.existsSync('dist/index.html')) {
        const stats = fs.statSync('dist');
        return { status: 'pass', message: `Build successful, output in dist/ (${stats.size} bytes)` };
      } else {
        return { status: 'fail', message: 'Build completed but no output found' };
      }
    } catch (err) {
      return { status: 'fail', message: `Build failed: ${err.message.split('\n')[0]}` };
    }
  },

  async testSuite() {
    try {
      execSync('npm test', { stdio: 'pipe' });
      return { status: 'pass', message: 'All tests passing' };
    } catch (err) {
      const output = err.stdout?.toString() || err.message;
      const failedMatch = output.match(/(\d+) failed/);
      const passedMatch = output.match(/(\d+) passed/);
      
      if (failedMatch && passedMatch) {
        const failed = parseInt(failedMatch[1]);
        const passed = parseInt(passedMatch[1]);
        const total = failed + passed;
        const passRate = Math.round((passed / total) * 100);
        
        if (passRate >= 80) {
          return { status: 'warn', message: `${passRate}% tests passing (${failed} failed, ${passed} passed)` };
        } else {
          return { status: 'fail', message: `Only ${passRate}% tests passing (${failed} failed, ${passed} passed)` };
        }
      } else {
        return { status: 'fail', message: 'Test suite failed to run' };
      }
    }
  },

  async pythonPipeline() {
    try {
      execSync('python scripts/test_pipeline.py', { stdio: 'pipe' });
      return { status: 'pass', message: 'Python data pipeline tests passing' };
    } catch (err) {
      return { status: 'fail', message: 'Python pipeline tests failed' };
    }
  },

  async securityCheck() {
    try {
      const auditOutput = execSync('npm audit --audit-level=high', { stdio: 'pipe' }).toString();
      
      if (auditOutput.includes('found 0 vulnerabilities')) {
        return { status: 'pass', message: 'No high-severity vulnerabilities found' };
      } else {
        const vulnMatch = auditOutput.match(/(\d+) high/);
        if (vulnMatch) {
          const count = parseInt(vulnMatch[1]);
          return { status: 'fail', message: `${count} high-severity vulnerabilities found` };
        } else {
          return { status: 'warn', message: 'Some vulnerabilities found, check npm audit output' };
        }
      }
    } catch (err) {
      return { status: 'warn', message: 'Could not run security audit' };
    }
  },

  async performanceCheck() {
    if (!fs.existsSync('dist')) {
      return { status: 'fail', message: 'No build output to analyze' };
    }
    
    try {
      // Check bundle sizes
      const jsFiles = execSync('find dist -name "*.js" -type f', { stdio: 'pipe' }).toString().trim().split('\n').filter(Boolean);
      const cssFiles = execSync('find dist -name "*.css" -type f', { stdio: 'pipe' }).toString().trim().split('\n').filter(Boolean);
      
      let totalSize = 0;
      [...jsFiles, ...cssFiles].forEach(file => {
        if (fs.existsSync(file)) {
          totalSize += fs.statSync(file).size;
        }
      });
      
      const sizeMB = totalSize / (1024 * 1024);
      
      if (sizeMB < 1.0) {
        return { status: 'pass', message: `Bundle size optimal (${sizeMB.toFixed(2)}MB)` };
      } else if (sizeMB < 2.0) {
        return { status: 'warn', message: `Bundle size acceptable (${sizeMB.toFixed(2)}MB)` };
      } else {
        return { status: 'fail', message: `Bundle size too large (${sizeMB.toFixed(2)}MB)` };
      }
    } catch (err) {
      return { status: 'warn', message: 'Could not analyze bundle size' };
    }
  },

  async seoOptimization() {
    try {
      const indexHtml = fs.readFileSync('index.html', 'utf8');
      
      const checks = [
        { test: /<title>.*<\/title>/, name: 'title tag' },
        { test: /<meta name="description"/, name: 'meta description' },
        { test: /<meta name="viewport"/, name: 'viewport meta' },
        { test: /<meta property="og:title"/, name: 'Open Graph title' },
        { test: /application\/ld\+json/, name: 'structured data' }
      ];
      
      const missing = checks.filter(check => !check.test.test(indexHtml));
      
      if (missing.length === 0) {
        return { status: 'pass', message: 'All SEO elements present' };
      } else if (missing.length <= 2) {
        return { status: 'warn', message: `Missing SEO elements: ${missing.map(m => m.name).join(', ')}` };
      } else {
        return { status: 'fail', message: `Missing critical SEO elements: ${missing.map(m => m.name).join(', ')}` };
      }
    } catch (err) {
      return { status: 'fail', message: 'Could not analyze SEO optimization' };
    }
  }
};

// Main execution
async function main() {
  const checker = new LaunchChecker();
  
  // Add all checks
  checker.addCheck('File Structure', checks.fileStructure, true);
  checker.addCheck('Data Files', checks.dataFiles, true);
  checker.addCheck('GitHub Workflows', checks.githubWorkflows, true);
  checker.addCheck('Package Dependencies', checks.packageDependencies, true);
  checker.addCheck('Build Process', checks.buildProcess, true);
  checker.addCheck('Test Suite', checks.testSuite, false);
  checker.addCheck('Python Pipeline', checks.pythonPipeline, true);
  checker.addCheck('Security Check', checks.securityCheck, false);
  checker.addCheck('Performance Check', checks.performanceCheck, false);
  checker.addCheck('SEO Optimization', checks.seoOptimization, false);
  
  const ready = await checker.runAll();
  
  if (ready) {
    header('Next Steps');
    info('1. Commit and push all changes to GitHub');
    info('2. Verify GitHub Pages is enabled in repository settings');
    info('3. Monitor the deployment in GitHub Actions');
    info('4. Test the live site after deployment');
    info('5. Set up monitoring and alerts');
    
    log('\n🚀 Ready for launch!', 'green');
    process.exit(0);
  } else {
    header('Required Actions');
    error('Fix the failed checks above before launching');
    error('Run this script again after making fixes');
    
    log('\n🚨 Not ready for launch', 'red');
    process.exit(1);
  }
}

// Handle errors
process.on('unhandledRejection', (err) => {
  error(`Unhandled error: ${err.message}`);
  process.exit(1);
});

// Run the checker
main().catch(err => {
  error(`Launch checker failed: ${err.message}`);
  process.exit(1);
});

export { LaunchChecker, checks };