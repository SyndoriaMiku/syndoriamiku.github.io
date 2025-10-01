/**
 * Path utility functions for GitHub Pages compatibility
 */

/**
 * Get relative path based on current location
 * @param {string} targetPath - Target path from root (e.g., "admin/index.html", "user/login.html")
 * @returns {string} - Relative path that works from current location
 */
function getRelativePath(targetPath) {
    const currentPath = window.location.pathname;
    
    // Remove leading slash and .html if present in targetPath
    const cleanTarget = targetPath.replace(/^\//, '').replace(/\.html$/, '');
    
    // Determine if we're in a subdirectory
    if (currentPath.includes('/user/') || currentPath.includes('/admin/') || 
        currentPath.includes('/ytg/') || currentPath.includes('/temple/') || 
        currentPath.includes('/gacha/')) {
        // We're in a subdirectory, need to go up one level
        if (cleanTarget === '' || cleanTarget === 'index') {
            return '../index.html';
        } else if (cleanTarget.startsWith('admin/')) {
            return '../' + cleanTarget + '.html';
        } else if (cleanTarget.startsWith('user/')) {
            return '../' + cleanTarget + '.html';
        } else if (cleanTarget.startsWith('ytg/')) {
            return '../' + cleanTarget + '.html';
        } else if (cleanTarget.startsWith('temple/')) {
            return '../' + cleanTarget + '.html';
        } else {
            return '../' + cleanTarget + '.html';
        }
    } else {
        // We're at root level
        if (cleanTarget === '' || cleanTarget === 'index') {
            return 'index.html';
        } else {
            return cleanTarget + '.html';
        }
    }
}

/**
 * Navigate to a page using relative paths
 * @param {string} targetPath - Target path from root
 */
function navigateToPage(targetPath) {
    const relativePath = getRelativePath(targetPath);
    window.location.href = relativePath;
}