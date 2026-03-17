/**
 * Scheduled Jobs Calendar Module
 * Handles calendar view, job management, and data fetching
 */

(function() {
  // State
  var currentDate = new Date();
  var jobs = [];
  var filteredJobs = [];
  var refreshInterval = null;
  var editingJobId = null;

  // DOM Elements
  var calendarGrid = null;
  var calendarTitle = null;
  var tooltip = null;
  var jobModal = null;
  var jobForm = null;

  /**
   * Initialize the calendar page
   */
  function init() {
    // Cache DOM elements
    calendarGrid = document.getElementById('calendar-grid');
    calendarTitle = document.getElementById('calendar-title');
    tooltip = document.getElementById('job-tooltip');
    jobModal = document.getElementById('job-modal');
    jobForm = document.getElementById('job-form');

    // Bind events
    bindEvents();

    // Load initial data
    loadJobs();

    // Set up auto-refresh every 30 seconds
    refreshInterval = setInterval(loadJobs, 30000);
  }

  /**
   * Bind event listeners
   */
  function bindEvents() {
    // Navigation
    document.getElementById('prev-month').addEventListener('click', function() {
      currentDate.setMonth(currentDate.getMonth() - 1);
      renderCalendar();
    });

    document.getElementById('next-month').addEventListener('click', function() {
      currentDate.setMonth(currentDate.getMonth() + 1);
      renderCalendar();
    });

    document.getElementById('today-btn').addEventListener('click', function() {
      currentDate = new Date();
      renderCalendar();
    });

    // Actions
    document.getElementById('refresh-btn').addEventListener('click', loadJobs);
    document.getElementById('new-job-btn').addEventListener('click', function() {
      openModal();
    });
    document.getElementById('empty-create-btn').addEventListener('click', function() {
      openModal();
    });

    // Filters
    document.getElementById('search-input').addEventListener('input', debounce(applyFilters, 300));
    document.getElementById('status-filter').addEventListener('change', applyFilters);
    document.getElementById('hide-disabled').addEventListener('change', applyFilters);

    // Modal
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('modal-cancel').addEventListener('click', closeModal);
    document.getElementById('modal-save').addEventListener('click', saveJob);
    document.getElementById('modal-delete').addEventListener('click', deleteJob);

    // Close modal on overlay click
    jobModal.addEventListener('click', function(e) {
      if (e.target === jobModal) {
        closeModal();
      }
    });

    // Close modal on Escape key
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && jobModal.classList.contains('visible')) {
        closeModal();
      }
    });
  }

  /**
   * Load jobs from the API
   */
  function loadJobs() {
    var loadingEl = document.getElementById('loading');
    if (loadingEl) loadingEl.style.display = 'block';

    // Hide empty state while loading
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('calendar-container').style.display = 'block';

    // Fetch all jobs (up to 1000 for calendar view)
    Auth.fetchWithAuth('/api/v1/admin/scheduled-jobs?per_page=1000')
      .then(function(response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      })
      .then(function(data) {
        if (loadingEl) loadingEl.style.display = 'none';

        jobs = data.items || [];
        applyFilters();

        // Show empty state if no jobs
        if (jobs.length === 0) {
          document.getElementById('empty-state').style.display = 'block';
          document.getElementById('calendar-container').style.display = 'none';
        }
      })
      .catch(function(err) {
        if (loadingEl) loadingEl.style.display = 'none';
        showError('Failed to load jobs: ' + err.message);
      });
  }

  /**
   * Apply filters to the jobs list
   */
  function applyFilters() {
    var searchTerm = document.getElementById('search-input').value.toLowerCase();
    var statusFilter = document.getElementById('status-filter').value;
    var hideDisabled = document.getElementById('hide-disabled').checked;

    filteredJobs = jobs.filter(function(job) {
      // Search filter
      if (searchTerm && job.name.toLowerCase().indexOf(searchTerm) === -1) {
        return false;
      }

      // Status filter
      if (statusFilter === 'enabled' && !job.enabled) return false;
      if (statusFilter === 'disabled' && job.enabled) return false;
      if (statusFilter === 'failed' && !job.last_error) return false;

      // Hide disabled toggle
      if (hideDisabled && !job.enabled) return false;

      return true;
    });

    renderCalendar();
  }

  /**
   * Render the calendar grid
   */
  function renderCalendar() {
    var year = currentDate.getFullYear();
    var month = currentDate.getMonth();

    // Update title
    var monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November', 'December'];
    calendarTitle.textContent = monthNames[month] + ' ' + year;

    // Get first day of month and number of days
    var firstDay = new Date(year, month, 1).getDay();
    var daysInMonth = new Date(year, month + 1, 0).getDate();
    var daysInPrevMonth = new Date(year, month, 0).getDate();

    // Today's date for highlighting
    var today = new Date();
    var isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

    var html = '';

    // Day headers
    var dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    for (var i = 0; i < 7; i++) {
      html += '<div class="calendar-day-header">' + dayHeaders[i] + '</div>';
    }

    // Previous month days
    for (var i = firstDay - 1; i >= 0; i--) {
      var dayNum = daysInPrevMonth - i;
      html += renderDayCell(year, month - 1, dayNum, true);
    }

    // Current month days
    for (var day = 1; day <= daysInMonth; day++) {
      var isToday = isCurrentMonth && today.getDate() === day;
      html += renderDayCell(year, month, day, false, isToday);
    }

    // Next month days to fill grid (6 rows * 7 cols = 42 cells total)
    var totalCells = firstDay + daysInMonth;
    var remainingCells = 42 - totalCells;
    for (var i = 1; i <= remainingCells; i++) {
      html += renderDayCell(year, month + 1, i, true);
    }

    calendarGrid.innerHTML = html;
    attachJobEventListeners();
  }

  /**
   * Render a single day cell
   */
  function renderDayCell(year, month, day, isOtherMonth, isToday) {
    // Normalize month/year for date comparison
    var date = new Date(year, month, day);
    var dateStr = formatDateKey(date);

    var classes = ['calendar-day'];
    if (isOtherMonth) classes.push('other-month');
    if (isToday) classes.push('today');

    // Find jobs for this day
    var dayJobs = filteredJobs.filter(function(job) {
      if (!job.next_run_at) return false;
      var jobDate = new Date(job.next_run_at);
      return formatDateKey(jobDate) === dateStr;
    });

    var html = '<div class="' + classes.join(' ') + '">';
    html += '<div class="calendar-day-number">' + day + '</div>';

    if (dayJobs.length > 0) {
      html += '<div class="calendar-jobs">';
      for (var i = 0; i < dayJobs.length; i++) {
        var job = dayJobs[i];
        var jobClass = 'calendar-job';
        if (job.last_error) {
          jobClass += ' failed';
        } else if (job.enabled) {
          jobClass += ' enabled';
        } else {
          jobClass += ' disabled';
        }
        html += '<div class="' + jobClass + '" data-job-id="' + job.id + '">' +
                escapeHtml(job.name) + '</div>';
      }
      html += '</div>';
    }

    html += '</div>';
    return html;
  }

  /**
   * Attach event listeners to job elements
   */
  function attachJobEventListeners() {
    var jobElements = calendarGrid.querySelectorAll('.calendar-job');
    for (var i = 0; i < jobElements.length; i++) {
      var el = jobElements[i];

      el.addEventListener('click', function(e) {
        e.stopPropagation();
        var jobId = this.getAttribute('data-job-id');
        var job = jobs.find(function(j) { return j.id === jobId; });
        if (job) {
          openModal(job);
        }
      });

      el.addEventListener('mouseenter', function(e) {
        var jobId = this.getAttribute('data-job-id');
        var job = jobs.find(function(j) { return j.id === jobId; });
        if (job) {
          showTooltip(e, job);
        }
      });

      el.addEventListener('mouseleave', hideTooltip);
    }
  }

  /**
   * Show tooltip for a job
   */
  function showTooltip(e, job) {
    var tooltipTitle = tooltip.querySelector('.job-tooltip-title');
    var tooltipTime = tooltip.querySelector('.job-tooltip-time');

    tooltipTitle.textContent = job.name;

    var timeText = '';
    if (job.next_run_at) {
      timeText += 'Next: ' + formatDateTime(new Date(job.next_run_at));
    }
    if (job.last_error) {
      timeText += (timeText ? ' • ' : '') + 'Has errors';
    }
    if (!job.enabled) {
      timeText += (timeText ? ' • ' : '') + 'Disabled';
    }

    tooltipTime.textContent = timeText || 'No scheduled run';

    // Position tooltip
    var rect = e.target.getBoundingClientRect();
    tooltip.style.left = (rect.left + window.scrollX) + 'px';
    tooltip.style.top = (rect.bottom + window.scrollY + 5) + 'px';
    tooltip.classList.add('visible');
  }

  /**
   * Hide tooltip
   */
  function hideTooltip() {
    tooltip.classList.remove('visible');
  }

  /**
   * Open modal for creating/editing a job
   */
  function openModal(job) {
    editingJobId = job ? job.id : null;

    var modalTitle = document.getElementById('modal-title');
    var deleteBtn = document.getElementById('modal-delete');

    if (job) {
      modalTitle.textContent = 'Edit Job';
      deleteBtn.style.display = 'inline-block';

      // Fill form
      document.getElementById('job-name').value = job.name || '';
      document.getElementById('job-description').value = job.description || '';
      document.getElementById('job-type').value = job.job_type || '';
      document.getElementById('job-cron').value = job.cron_expression || '';
      document.getElementById('job-enabled').checked = job.enabled;

      if (job.next_run_at) {
        document.getElementById('job-next-run').value = formatDateTimeLocal(new Date(job.next_run_at));
      } else {
        document.getElementById('job-next-run').value = '';
      }
    } else {
      modalTitle.textContent = 'New Job';
      deleteBtn.style.display = 'none';

      // Clear form
      jobForm.reset();
      document.getElementById('job-enabled').checked = true;
    }

    jobModal.classList.add('visible');
  }

  /**
   * Close modal
   */
  function closeModal() {
    jobModal.classList.remove('visible');
    editingJobId = null;
  }

  /**
   * Save job (create or update)
   */
  function saveJob() {
    var name = document.getElementById('job-name').value.trim();
    var description = document.getElementById('job-description').value.trim();
    var jobType = document.getElementById('job-type').value.trim();
    var cronExpression = document.getElementById('job-cron').value.trim();
    var nextRunAt = document.getElementById('job-next-run').value;
    var enabled = document.getElementById('job-enabled').checked;

    // Validation
    if (!name || !jobType || !cronExpression) {
      alert('Please fill in all required fields');
      return;
    }

    var payload = {
      name: name,
      description: description,
      job_type: jobType,
      cron_expression: cronExpression,
      enabled: enabled
    };

    if (nextRunAt) {
      payload.next_run_at = new Date(nextRunAt).toISOString();
    }

    var url = '/api/v1/admin/scheduled-jobs';
    var method = 'POST';

    if (editingJobId) {
      url += '/' + editingJobId;
      method = 'PATCH';
    }

    Auth.fetchWithAuth(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(function(err) {
          throw new Error(err.error || 'Failed to save job');
        });
      }
      return response.json();
    })
    .then(function() {
      closeModal();
      loadJobs(); // Refresh calendar
    })
    .catch(function(err) {
      alert('Error: ' + err.message);
    });
  }

  /**
   * Delete current job
   */
  function deleteJob() {
    if (!editingJobId) return;

    if (!confirm('Are you sure you want to delete this job?')) {
      return;
    }

    Auth.fetchWithAuth('/api/v1/admin/scheduled-jobs/' + editingJobId, {
      method: 'DELETE'
    })
    .then(function(response) {
      if (!response.ok) {
        throw new Error('Failed to delete job');
      }
      closeModal();
      loadJobs(); // Refresh calendar
    })
    .catch(function(err) {
      alert('Error: ' + err.message);
    });
  }

  /**
   * Show error message
   */
  function showError(message) {
    var errorEl = document.getElementById('error');
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.style.display = 'block';
    }
  }

  /**
   * Format date as YYYY-MM-DD for comparison
   */
  function formatDateKey(date) {
    var year = date.getFullYear();
    var month = String(date.getMonth() + 1).padStart(2, '0');
    var day = String(date.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
  }

  /**
   * Format date and time for display
   */
  function formatDateTime(date) {
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  /**
   * Format date for datetime-local input
   */
  function formatDateTimeLocal(date) {
    var year = date.getFullYear();
    var month = String(date.getMonth() + 1).padStart(2, '0');
    var day = String(date.getDate()).padStart(2, '0');
    var hours = String(date.getHours()).padStart(2, '0');
    var minutes = String(date.getMinutes()).padStart(2, '0');
    return year + '-' + month + '-' + day + 'T' + hours + ':' + minutes;
  }

  /**
   * Escape HTML special characters
   */
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * Debounce function
   */
  function debounce(func, wait) {
    var timeout;
    return function() {
      var context = this;
      var args = arguments;
      clearTimeout(timeout);
      timeout = setTimeout(function() {
        func.apply(context, args);
      }, wait);
    };
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
