#!/usr/bin/env node

/**
 * GGUF Model Index - Build Optimization Script
 * ============================================
 * This script analyzes and optimizes the build output
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Colors for console output
const colors = {
    reset: '\x1b[0m',
    bright: '\x1b[1m',
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

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function analyzeDirectory(dirPath, basePath = '') {
    const items = [];
    
    if (!fs.existsSync(dirPath)) {
        return items;
    }
    
    const files = fs.readdirSync(dirPath);
    
    for (const file of files) {
        const filePath = path.join(dirPath, file);
        const relativePath = path.join(basePath, file);
        const stats = fs.statSync(filePath);
        
        if (stats.isDirectory()) {
            items.push(...analyzeDirectory(filePath, relativePath));
        } else {
            items.push({
                path: relativePath,
                size: stats.size,
                type: path.extname(file).toLowerCase()
            });
        }
    }
    
    return items;
}

function analyzeBuild() {
    log('\n📊 Build Analysis Report', 'cyan');
    log('========================', 'cyan');
    
    const distPath = path.join(__dirname, '..', 'dist');
    
    if (!fs.existsSync(distPath)) {
        log('❌ Build directory not found. Run npm run build first.', 'red');
        process.exit(1);
    }
    
    const files = analyzeDirectory(distPath);
    
    // Calculate total size
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    log(`\n📦 Total build size: ${formatBytes(totalSize)}`, 'bright');
    
    // Group by file type
    const byType = files.reduce((acc, file) => {
        const type = file.type || 'other';
        if (!acc[type]) acc[type] = { count: 0, size: 0, files: [] };
        acc[type].count++;
        acc[type].size += file.size;
        acc[type].files.push(file);
        return acc;
    }, {});
    
    // Display breakdown by type
    log('\n📋 File Type Breakdown:', 'blue');
    Object.entries(byType)
        .sort(([,a], [,b]) => b.size - a.size)
        .forEach(([type, data]) => {
            const percentage = ((data.size / totalSize) * 100).toFixed(1);
            log(`  ${type.padEnd(8)} ${data.count.toString().padStart(3)} files  ${formatBytes(data.size).padStart(8)} (${percentage}%)`, 'yellow');
        });
    
    // Find largest files
    log('\n🔍 Largest Files:', 'blue');
    files
        .sort((a, b) => b.size - a.size)
        .slice(0, 10)
        .forEach(file => {
            log(`  ${file.path.padEnd(40)} ${formatBytes(file.size).padStart(8)}`, 'yellow');
        });
    
    // Performance recommendations
    log('\n💡 Optimization Recommendations:', 'green');
    
    const jsFiles = byType['.js'] || { size: 0, files: [] };
    const cssFiles = byType['.css'] || { size: 0, files: [] };
    const imageFiles = [...(byType['.png'] || { files: [] }).files, 
                       ...(byType['.jpg'] || { files: [] }).files,
                       ...(byType['.jpeg'] || { files: [] }).files,
                       ...(byType['.svg'] || { files: [] }).files];
    
    // JavaScript recommendations
    if (jsFiles.size > 500 * 1024) { // 500KB
        log('  ⚠️  JavaScript bundle is large (>500KB). Consider code splitting.', 'yellow');
    } else if (jsFiles.size > 100 * 1024) { // 100KB
        log('  ✅ JavaScript bundle size is reasonable.', 'green');
    } else {
        log('  ✅ JavaScript bundle is well optimized.', 'green');
    }
    
    // CSS recommendations
    if (cssFiles.size > 100 * 1024) { // 100KB
        log('  ⚠️  CSS bundle is large (>100KB). Consider removing unused styles.', 'yellow');
    } else {
        log('  ✅ CSS bundle size is good.', 'green');
    }
    
    // Image recommendations
    if (imageFiles.length > 0) {
        const largeImages = imageFiles.filter(img => img.size > 100 * 1024);
        if (largeImages.length > 0) {
            log(`  ⚠️  ${largeImages.length} large images found (>100KB). Consider optimization.`, 'yellow');
        } else {
            log('  ✅ Image sizes are optimized.', 'green');
        }
    }
    
    // Overall recommendations
    if (totalSize > 2 * 1024 * 1024) { // 2MB
        log('  ⚠️  Total build size is large (>2MB). Consider lazy loading.', 'yellow');
    } else if (totalSize > 1 * 1024 * 1024) { // 1MB
        log('  ✅ Total build size is acceptable.', 'green');
    } else {
        log('  ✅ Total build size is excellent.', 'green');
    }
    
    // Check for critical files
    log('\n🔍 Critical Files Check:', 'blue');
    const criticalFiles = ['index.html', 'assets/index.js', 'assets/index.css'];
    
    criticalFiles.forEach(criticalFile => {
        const exists = files.some(file => file.path.includes(criticalFile.split('/').pop()));
        if (exists) {
            log(`  ✅ ${criticalFile}`, 'green');
        } else {
            log(`  ❌ ${criticalFile} - Missing!`, 'red');
        }
    });
    
    // Check for data files
    const hasDataFiles = files.some(file => file.path.includes('models.json') || file.path.includes('data/'));
    if (hasDataFiles) {
        log('  ✅ Model data files present', 'green');
    } else {
        log('  ⚠️  Model data files not found', 'yellow');
    }
    
    // Check for SEO files
    const hasSitemap = files.some(file => file.path.includes('sitemap.xml'));
    const hasRobots = files.some(file => file.path.includes('robots.txt'));
    
    if (hasSitemap) log('  ✅ sitemap.xml present', 'green');
    else log('  ⚠️  sitemap.xml missing', 'yellow');
    
    if (hasRobots) log('  ✅ robots.txt present', 'green');
    else log('  ⚠️  robots.txt missing', 'yellow');
    
    log('\n📈 Performance Score:', 'magenta');
    let score = 100;
    
    if (totalSize > 2 * 1024 * 1024) score -= 20;
    else if (totalSize > 1 * 1024 * 1024) score -= 10;
    
    if (jsFiles.size > 500 * 1024) score -= 15;
    else if (jsFiles.size > 100 * 1024) score -= 5;
    
    if (cssFiles.size > 100 * 1024) score -= 10;
    
    if (!hasSitemap || !hasRobots) score -= 5;
    
    const scoreColor = score >= 90 ? 'green' : score >= 70 ? 'yellow' : 'red';
    log(`  ${score}/100`, scoreColor);
    
    if (score >= 90) {
        log('  🎉 Excellent! Your build is well optimized.', 'green');
    } else if (score >= 70) {
        log('  👍 Good! Some optimizations could improve performance.', 'yellow');
    } else {
        log('  ⚠️  Needs improvement. Consider the recommendations above.', 'red');
    }
    
    log('\n✨ Analysis complete!', 'cyan');
}

// Run the analysis
analyzeBuild();