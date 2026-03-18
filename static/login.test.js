/**
 * Login Page UI Tests
 * Tests for login page layout and styling
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
  console.log('Running Login Page UI Tests...\n');
  
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
// Remember Me Checkbox Layout Tests
// ============================================================================

/**
 * Checks if the computed display style for an element matches expected value
 */
function getComputedDisplay(selector) {
  var element = document.querySelector(selector);
  if (!element) {
    throw new Error('Element not found: ' + selector);
  }
  return window.getComputedStyle(element).display;
}

/**
 * Checks if the computed align-items style for an element matches expected value
 */
function getComputedAlignItems(selector) {
  var element = document.querySelector(selector);
  if (!element) {
    throw new Error('Element not found: ' + selector);
  }
  return window.getComputedStyle(element).alignItems;
}

/**
 * Checks if the computed flex-direction style for an element matches expected value
 */
function getComputedFlexDirection(selector) {
  var element = document.querySelector(selector);
  if (!element) {
    throw new Error('Element not found: ' + selector);
  }
  return window.getComputedStyle(element).flexDirection;
}

test('checkbox label uses flexbox display', function() {
  var display = getComputedDisplay('.remember-me .checkbox-label');
  assertEqual(display, 'flex', 'Checkbox label should use flexbox display');
});

test('checkbox label has horizontal alignment', function() {
  var flexDirection = getComputedFlexDirection('.remember-me .checkbox-label');
  assertEqual(flexDirection, 'row', 'Checkbox label should use row flex direction for horizontal layout');
});

test('checkbox label has center alignment', function() {
  var alignItems = getComputedAlignItems('.remember-me .checkbox-label');
  assertEqual(alignItems, 'center', 'Checkbox label should vertically center items');
});

test('checkbox input is not full width', function() {
  var checkbox = document.querySelector('.remember-me input[type="checkbox"]');
  if (!checkbox) {
    throw new Error('Checkbox input not found');
  }
  var width = window.getComputedStyle(checkbox).width;
  assertFalse(width === '100%' || width === document.querySelector('.remember-me').clientWidth + 'px', 
    'Checkbox should not be full width');
});

test('remember me container exists', function() {
  var container = document.querySelector('.remember-me');
  assertTrue(!!container, 'Remember me container should exist');
});

test('checkbox and label text are inline', function() {
  var label = document.querySelector('.remember-me .checkbox-label');
  if (!label) {
    throw new Error('Checkbox label not found');
  }
  
  var checkbox = label.querySelector('input[type="checkbox"]');
  var textSpan = label.querySelector('span');
  
  assertTrue(!!checkbox, 'Checkbox input should exist inside label');
  assertTrue(!!textSpan, 'Text span should exist inside label');
  
  // Check that they're siblings (both direct children of the label)
  assertTrue(checkbox.parentElement === label, 'Checkbox should be direct child of label');
  assertTrue(textSpan.parentElement === label, 'Text span should be direct child of label');
});

// ============================================================================
// Run Tests
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { runTests: runTests };
}

// Run tests when in browser environment
if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', runTests);
  } else {
    runTests();
  }
}
