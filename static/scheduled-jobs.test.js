/**
 * Scheduled Jobs Tests
 * Tests for cron validation, human-readable descriptions, and next run calculations
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

function assertContains(haystack, needle, message) {
  if (haystack.indexOf(needle) === -1) {
    throw new Error((message || 'String does not contain expected value') + ': expected "' + needle + '" in "' + haystack + '"');
  }
}

// Run all tests
function runTests() {
  console.log('Running Scheduled Jobs Tests...\n');
  
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
// Cron Validation Tests
// ============================================================================

function isValidCron(cron) {
  var parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) {
    return false;
  }
  
  var ranges = [
    { min: 0, max: 59 },   // minute
    { min: 0, max: 23 },   // hour
    { min: 1, max: 31 },   // day of month
    { min: 1, max: 12 },   // month
    { min: 0, max: 7 }     // day of week
  ];
  
  for (var i = 0; i < 5; i++) {
    if (!isValidCronField(parts[i], ranges[i].min, ranges[i].max)) {
      return false;
    }
  }
  
  return true;
}

function isValidCronField(field, min, max) {
  if (field === '*') {
    return true;
  }
  
  // Handle step values (e.g., */5, 1-10/2)
  if (field.indexOf('/') !== -1) {
    var stepParts = field.split('/');
    if (stepParts.length !== 2) {
      return false;
    }
    var step = parseInt(stepParts[1], 10);
    if (isNaN(step) || step < 1) {
      return false;
    }
    var baseField = stepParts[0];
    // Base can be * or a range
    if (baseField === '*') {
      return true;
    }
    if (baseField.indexOf('-') !== -1) {
      var rangeParts = baseField.split('-');
      if (rangeParts.length !== 2) {
        return false;
      }
      var start = parseInt(rangeParts[0], 10);
      var end = parseInt(rangeParts[1], 10);
      if (isNaN(start) || isNaN(end)) {
        return false;
      }
      if (start < min || end > max || start > end) {
        return false;
      }
      return true;
    }
    // Base can also be a single number
    var baseVal = parseInt(baseField, 10);
    if (isNaN(baseVal) || baseVal < min || baseVal > max) {
      return false;
    }
    return true;
  }
  
  if (field.indexOf('-') !== -1) {
    var rangeParts = field.split('-');
    if (rangeParts.length !== 2) {
      return false;
    }
    var start = parseInt(rangeParts[0], 10);
    var end = parseInt(rangeParts[1], 10);
    if (isNaN(start) || isNaN(end)) {
      return false;
    }
    if (start < min || end > max || start > end) {
      return false;
    }
    return true;
  }
  
  if (field.indexOf(',') !== -1) {
    var values = field.split(',');
    for (var i = 0; i < values.length; i++) {
      var val = parseInt(values[i], 10);
      if (isNaN(val) || val < min || val > max) {
        return false;
      }
    }
    return true;
  }
  
  var singleVal = parseInt(field, 10);
  if (isNaN(singleVal)) {
    return false;
  }
  if (min === 0 && max === 7 && singleVal === 7) {
    return true;
  }
  return singleVal >= min && singleVal <= max;
}

test('validates every minute cron (* * * * *)', function() {
  assertTrue(isValidCron('* * * * *'), 'Should accept every minute');
});

test('validates daily at 2 AM (0 2 * * *)', function() {
  assertTrue(isValidCron('0 2 * * *'), 'Should accept daily at 2 AM');
});

test('validates weekly on Monday at 9 AM (0 9 * * 1)', function() {
  assertTrue(isValidCron('0 9 * * 1'), 'Should accept weekly on Monday');
});

test('validates monthly on 1st at midnight (0 0 1 * *)', function() {
  assertTrue(isValidCron('0 0 1 * *'), 'Should accept monthly');
});

test('validates every 5 minutes (*/5 * * * *)', function() {
  assertTrue(isValidCron('*/5 * * * *'), 'Should accept step values');
});

test('validates range values (0 9-17 * * 1-5)', function() {
  assertTrue(isValidCron('0 9-17 * * 1-5'), 'Should accept range values');
});

test('validates list values (0 9,12,15 * * *)', function() {
  assertTrue(isValidCron('0 9,12,15 * * *'), 'Should accept list values');
});

test('validates day of week 7 as Sunday (0 0 * * 7)', function() {
  assertTrue(isValidCron('0 0 * * 7'), 'Should accept 7 as Sunday');
});

test('rejects invalid cron with 4 parts', function() {
  assertFalse(isValidCron('0 2 * *'), 'Should reject 4-part cron');
});

test('rejects invalid cron with 6 parts', function() {
  assertFalse(isValidCron('0 2 * * * *'), 'Should reject 6-part cron');
});

test('rejects invalid minute value (60)', function() {
  assertFalse(isValidCron('60 2 * * *'), 'Should reject minute 60');
});

test('rejects invalid hour value (24)', function() {
  assertFalse(isValidCron('0 24 * * *'), 'Should reject hour 24');
});

test('rejects invalid day of month (32)', function() {
  assertFalse(isValidCron('0 0 32 * *'), 'Should reject day 32');
});

test('rejects invalid month (13)', function() {
  assertFalse(isValidCron('0 0 1 13 *'), 'Should reject month 13');
});

test('rejects invalid day of week (8)', function() {
  assertFalse(isValidCron('0 0 * * 8'), 'Should reject day of week 8');
});

test('rejects invalid characters in cron', function() {
  assertFalse(isValidCron('abc def * * *'), 'Should reject invalid characters');
});

// ============================================================================
// Cron Description Tests
// ============================================================================

function getCronDescription(cron) {
  var parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) {
    return null;
  }
  
  var minute = parts[0];
  var hour = parts[1];
  var dom = parts[2];
  var month = parts[3];
  var dow = parts[4];
  
  // Every minute
  if (cron === '* * * * *') {
    return 'Every minute';
  }
  
  // Every X minutes (e.g., */5)
  if (minute.indexOf('*/') === 0 && hour === '*' && dom === '*' && month === '*' && dow === '*') {
    var interval = minute.split('/')[1];
    return 'Every ' + interval + ' minutes';
  }
  
  // Every hour at specific minute (only single digit minute, not ranges)
  if (minute !== '*' && !isNaN(parseInt(minute, 10)) && parseInt(minute, 10).toString() === minute && hour === '*' && dom === '*' && month === '*' && dow === '*') {
    return 'Every hour at minute ' + minute;
  }
  
  // Daily at specific time
  if (dom === '*' && month === '*' && dow === '*' && hour !== '*' && minute !== '*') {
    var time = formatTime(parseInt(hour, 10), parseInt(minute, 10));
    return 'Every day at ' + time;
  }
  
  // Weekly on specific day (only single digit dow, not ranges)
  if (dom === '*' && month === '*' && dow !== '*' && dow.indexOf('-') === -1 && dow.indexOf(',') === -1 && dow.indexOf('/') === -1) {
    var days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    var dayNum = parseInt(dow, 10);
    var dayName = days[dayNum % 7];
    var time = formatTime(parseInt(hour, 10), parseInt(minute, 10));
    return 'Every ' + dayName + ' at ' + time;
  }
  
  // Monthly on specific day (only single digit dom, not ranges)
  if (dom !== '*' && dom.indexOf('-') === -1 && dom.indexOf(',') === -1 && dom.indexOf('/') === -1 && month === '*' && dow === '*') {
    var time = formatTime(parseInt(hour, 10), parseInt(minute, 10));
    return 'On day ' + dom + ' of every month at ' + time;
  }
  
  return null;
}

function formatTime(hour, minute) {
  var period = hour >= 12 ? 'PM' : 'AM';
  var displayHour = hour % 12;
  if (displayHour === 0) {
    displayHour = 12;
  }
  var displayMinute = minute < 10 ? '0' + minute : minute;
  return displayHour + ':' + displayMinute + ' ' + period;
}

test('describes every minute', function() {
  assertEqual(getCronDescription('* * * * *'), 'Every minute');
});

test('describes every hour at specific minute', function() {
  assertEqual(getCronDescription('30 * * * *'), 'Every hour at minute 30');
});

test('describes daily at 2 AM', function() {
  assertEqual(getCronDescription('0 2 * * *'), 'Every day at 2:00 AM');
});

test('describes daily at 2:30 PM', function() {
  assertEqual(getCronDescription('30 14 * * *'), 'Every day at 2:30 PM');
});

test('describes weekly on Monday at 9 AM', function() {
  assertEqual(getCronDescription('0 9 * * 1'), 'Every Monday at 9:00 AM');
});

test('describes weekly on Sunday at midnight', function() {
  assertEqual(getCronDescription('0 0 * * 0'), 'Every Sunday at 12:00 AM');
});

test('describes monthly on 1st at midnight', function() {
  assertEqual(getCronDescription('0 0 1 * *'), 'On day 1 of every month at 12:00 AM');
});

test('describes monthly on 15th at 3:30 PM', function() {
  assertEqual(getCronDescription('30 15 15 * *'), 'On day 15 of every month at 3:30 PM');
});

test('describes every 5 minutes', function() {
  assertEqual(getCronDescription('*/5 * * * *'), 'Every 5 minutes');
});

test('describes every 15 minutes', function() {
  assertEqual(getCronDescription('*/15 * * * *'), 'Every 15 minutes');
});

test('returns null for complex cron', function() {
  assertEqual(getCronDescription('0 9-17 * * 1-5'), null);
});

test('formatTime formats midnight correctly', function() {
  assertEqual(formatTime(0, 0), '12:00 AM');
});

test('formatTime formats noon correctly', function() {
  assertEqual(formatTime(12, 0), '12:00 PM');
});

test('formatTime formats 2 PM correctly', function() {
  assertEqual(formatTime(14, 30), '2:30 PM');
});

test('formatTime pads minutes correctly', function() {
  assertEqual(formatTime(9, 5), '9:05 AM');
});

// ============================================================================
// JSON Validation Tests
// ============================================================================

function isValidJSON(str) {
  try {
    JSON.parse(str);
    return true;
  } catch (e) {
    return false;
  }
}

test('validates empty object JSON', function() {
  assertTrue(isValidJSON('{}'), 'Should accept empty object');
});

test('validates simple object JSON', function() {
  assertTrue(isValidJSON('{"key": "value"}'), 'Should accept simple object');
});

test('validates array JSON', function() {
  assertTrue(isValidJSON('[1, 2, 3]'), 'Should accept array');
});

test('validates nested object JSON', function() {
  assertTrue(isValidJSON('{"outer": {"inner": "value"}}'), 'Should accept nested object');
});

test('rejects invalid JSON', function() {
  assertFalse(isValidJSON('{invalid}'), 'Should reject invalid JSON');
});

test('rejects trailing comma JSON', function() {
  assertFalse(isValidJSON('{"key": "value",}'), 'Should reject trailing comma');
});

test('rejects unquoted keys JSON', function() {
  assertFalse(isValidJSON('{key: "value"}'), 'Should reject unquoted keys');
});

// ============================================================================
// Escape HTML Tests
// ============================================================================

function escapeHtml(str) {
  if (str === null || str === undefined) {
    return '';
  }
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

test('escapes ampersand', function() {
  assertEqual(escapeHtml('a & b'), 'a &amp; b');
});

test('escapes less than', function() {
  assertEqual(escapeHtml('a < b'), 'a &lt; b');
});

test('escapes greater than', function() {
  assertEqual(escapeHtml('a > b'), 'a &gt; b');
});

test('escapes double quotes', function() {
  assertEqual(escapeHtml('say "hello"'), 'say &quot;hello&quot;');
});

test('escapes single quotes', function() {
  assertEqual(escapeHtml("it's"), 'it&#39;s');
});

test('escapes script tag', function() {
  assertEqual(escapeHtml('<script>alert("xss")</script>'), '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;');
});

test('handles null', function() {
  assertEqual(escapeHtml(null), '');
});

test('handles undefined', function() {
  assertEqual(escapeHtml(undefined), '');
});

test('handles empty string', function() {
  assertEqual(escapeHtml(''), '');
});

test('handles number', function() {
  assertEqual(escapeHtml(123), '123');
});

// ============================================================================
// Run Tests
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { runTests: runTests };
}

// Run tests if this file is executed directly
if (typeof require !== 'undefined' && require.main === module) {
  var success = runTests();
  process.exit(success ? 0 : 1);
}
