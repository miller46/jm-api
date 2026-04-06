/**
 * Auth Module Tests
 * Tests for login redirect functionality and URL validation
 */

// Test runner
var tests = [];
var passed = 0;
var failed = 0;

function test(name, fn) {
  tests.push({ name: name, fn: fn });
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error((message || 'Assertion failed') + ': expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
  }
}

function assertTrue(value, message) {
  if (value !== true) {
    throw new Error(message || 'Expected true, got ' + JSON.stringify(value));
  }
}

function assertFalse(value, message) {
  if (value !== false) {
    throw new Error(message || 'Expected false, got ' + JSON.stringify(value));
  }
}

// Run all tests
function runTests() {
  console.log('Running Auth Module Tests...\n');
  
  for (var i = 0; i < tests.length; i++) {
    var t = tests[i];
    try {
      t.fn();
      console.log('✅ ' + t.name);
      passed++;
    } catch (e) {
      console.log('❌ ' + t.name);
      console.log('   Error: ' + e.message);
      failed++;
    }
  }
  
  console.log('\n-------------------');
  console.log('Passed: ' + passed);
  console.log('Failed: ' + failed);
  console.log('Total:  ' + tests.length);
  
  return failed === 0;
}

// ============================================================================
// Get Safe Redirect URL Tests (from Auth.getSafeRedirectUrl)
// ============================================================================

function getSafeRedirectUrl(searchString) {
  var params = new URLSearchParams(searchString);
  var redirectTo = params.get('redirect');
  
  if (!redirectTo) {
    return '/admin/';
  }
  
  // Decode the redirect parameter
  var decodedRedirect = decodeURIComponent(redirectTo);
  
  // Only allow same-origin relative paths (start with /)
  // or known safe paths within the app
  if (decodedRedirect.charAt(0) === '/') {
    // Absolute path - ensure it's to a known HTML file or root
    var pathWithoutQuery = decodedRedirect.split('?')[0];
    // Allow paths that end with .html or are root /
    if (pathWithoutQuery.endsWith('.html') || pathWithoutQuery === '/') {
      return decodedRedirect;
    }
  } else if (decodedRedirect.indexOf('://') === -1 && decodedRedirect.indexOf('//') !== 0) {
    // Relative path without protocol - check against allowlist
    var cleanPath = decodedRedirect.split('?')[0];
    // Allow .html files in the same directory
    if (cleanPath.endsWith('.html') && cleanPath.indexOf('/') === -1) {
      return decodedRedirect;
    }
  }
  
  // Default fallback for unsafe redirects
  return '/admin/';
}

test('returns admin path when no redirect param', function() {
  assertEqual(getSafeRedirectUrl(''), '/admin/', 'Should return /admin/ when no redirect param');
});

test('returns admin path for empty redirect param', function() {
  assertEqual(getSafeRedirectUrl('?redirect='), '/admin/', 'Should return /admin/ for empty redirect');
});

test('returns admin path as default fallback', function() {
  assertEqual(getSafeRedirectUrl('?'), '/admin/', 'Should return /admin/ as default');
});

test('allows root path redirect', function() {
  assertEqual(getSafeRedirectUrl('?redirect=%2F'), '/', 'Should allow / redirect');
});

test('allows absolute path to html file', function() {
  assertEqual(getSafeRedirectUrl('?redirect=%2Ftable.html'), '/table.html', 'Should allow /table.html');
});

test('allows absolute path with query params', function() {
  assertEqual(getSafeRedirectUrl('?redirect=%2Ftable.html%3Ftable%3Dbots'), '/table.html?table=bots', 'Should allow /table.html?table=bots');
});

test('allows relative html file path', function() {
  assertEqual(getSafeRedirectUrl('?redirect=index.html'), 'index.html', 'Should allow relative index.html');
});

test('allows relative path to edit.html', function() {
  assertEqual(getSafeRedirectUrl('?redirect=edit.html'), 'edit.html', 'Should allow edit.html');
});

test('rejects external URL with http protocol', function() {
  assertEqual(getSafeRedirectUrl('?redirect=http%3A%2F%2Fevil.com'), '/admin/', 'Should reject http://evil.com');
});

test('rejects external URL with https protocol', function() {
  assertEqual(getSafeRedirectUrl('?redirect=https%3A%2F%2Fevil.com'), '/admin/', 'Should reject https://evil.com');
});

test('rejects protocol-relative URL', function() {
  assertEqual(getSafeRedirectUrl('?redirect=%2F%2Fevil.com'), '/admin/', 'Should reject //evil.com');
});

test('rejects path with directory traversal', function() {
  assertEqual(getSafeRedirectUrl('?redirect=..%2F..%2Fetc%2Fpasswd'), '/admin/', 'Should reject directory traversal');
});

test('rejects javascript protocol', function() {
  assertEqual(getSafeRedirectUrl('?redirect=javascript%3Aalert(1)'), '/admin/', 'Should reject javascript: protocol');
});

test('rejects non-html file extensions', function() {
  assertEqual(getSafeRedirectUrl('?redirect=%2Fapi%2Fsecret'), '/admin/', 'Should reject non-html paths');
});

test('rejects data URI', function() {
  assertEqual(getSafeRedirectUrl('?redirect=data%3Atext%2Fhtml%3Bbase64%2Cxxx'), '/admin/', 'Should reject data: URI');
});

test('decodes URL-encoded redirect parameter', function() {
  assertEqual(getSafeRedirectUrl('?redirect=%2Ftable.html%3Ftable%3Dbots%26page%3D1'), '/table.html?table=bots&page=1', 'Should decode URL-encoded params');
});

test('allows scheduled-jobs.html', function() {
  assertEqual(getSafeRedirectUrl('?redirect=scheduled-jobs.html'), 'scheduled-jobs.html', 'Should allow scheduled-jobs.html');
});

test('allows create.html with query params', function() {
  assertEqual(getSafeRedirectUrl('?redirect=create.html%3Ftable%3Dbots'), 'create.html?table=bots', 'Should allow create.html with params');
});

// ============================================================================
// Run Tests
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { runTests: runTests, getSafeRedirectUrl: getSafeRedirectUrl };
}

// Run tests if this file is executed directly
if (typeof require !== 'undefined' && require.main === module) {
  var success = runTests();
  process.exit(success ? 0 : 1);
}
