/**
 * Scheduled Jobs Module
 * Handles CRUD operations for scheduled jobs with real-time cron validation
 */

(function() {
  'use strict';

  // Module state
  var jobs = [];
  var currentJobId = null;
  var isSubmitting = false;

  // DOM element references (initialized on load)
  var elements = {};

  /**
   * Initialize the scheduled jobs page
   */
  function init() {
    cacheElements();
    bindEvents();
    loadJobs();
  }

  /**
   * Cache DOM element references
   */
  function cacheElements() {
    elements.loading = document.getElementById('loading');
    elements.error = document.getElementById('error');
    elements.jobsContainer = document.getElementById('jobs-container');
    elements.jobsTable = document.getElementById('jobs-table');
    elements.tableHead = document.getElementById('table-head');
    elements.tableBody = document.getElementById('table-body');
    elements.emptyState = document.getElementById('empty-state');
    elements.createJobBtn = document.getElementById('create-job-btn');
    
    // Modal elements
    elements.modal = document.getElementById('job-modal');
    elements.modalTitle = document.getElementById('modal-title');
    elements.modalCloseBtn = document.getElementById('modal-close-btn');
    elements.jobForm = document.getElementById('job-form');
    elements.jobId = document.getElementById('job-id');
    elements.jobName = document.getElementById('job-name');
    elements.jobDescription = document.getElementById('job-description');
    elements.jobCron = document.getElementById('job-cron');
    elements.jobPayload = document.getElementById('job-payload');
    elements.jobEnabled = document.getElementById('job-enabled');
    elements.modalFooterCreate = document.getElementById('modal-footer-create');
    elements.modalFooterEdit = document.getElementById('modal-footer-edit');
    elements.cancelBtn = document.getElementById('cancel-btn');
    elements.cancelBtnEdit = document.getElementById('cancel-btn-edit');
    elements.submitBtn = document.getElementById('submit-btn');
    elements.saveBtn = document.getElementById('save-btn');
    elements.createRunBtn = document.getElementById('create-run-btn');
    elements.runNowBtn = document.getElementById('run-now-btn');
    elements.deleteBtn = document.getElementById('delete-btn');
    
    // Cron helper elements
    elements.cronHelper = document.getElementById('cron-helper');
    elements.cronStatus = document.getElementById('cron-status');
    elements.cronHumanReadable = document.getElementById('cron-human-readable');
    elements.cronNextRuns = document.getElementById('cron-next-runs');
    
    // Error elements
    elements.nameError = document.getElementById('name-error');
    elements.cronError = document.getElementById('cron-error');
    elements.payloadError = document.getElementById('payload-error');
    
    // Delete modal elements
    elements.deleteModal = document.getElementById('delete-modal');
    elements.deleteModalClose = document.getElementById('delete-modal-close');
    elements.deleteJobName = document.getElementById('delete-job-name');
    elements.deleteCancelBtn = document.getElementById('delete-cancel-btn');
    elements.deleteConfirmBtn = document.getElementById('delete-confirm-btn');
    
    // Toast container
    elements.toastContainer = document.getElementById('toast-container');
  }

  /**
   * Bind event listeners
   */
  function bindEvents() {
    // Create button
    if (elements.createJobBtn) {
      elements.createJobBtn.addEventListener('click', openCreateModal);
    }
    
    // Modal close actions
    if (elements.modalCloseBtn) {
      elements.modalCloseBtn.addEventListener('click', closeModal);
    }
    if (elements.cancelBtn) {
      elements.cancelBtn.addEventListener('click', closeModal);
    }
    if (elements.cancelBtnEdit) {
      elements.cancelBtnEdit.addEventListener('click', closeModal);
    }
    if (elements.modal) {
      elements.modal.addEventListener('click', function(e) {
        if (e.target.classList.contains('modal-overlay')) {
          closeModal();
        }
      });
    }
    
    // Form submission
    if (elements.jobForm) {
      elements.jobForm.addEventListener('submit', handleFormSubmit);
    }
    
    // Real-time cron validation
    if (elements.jobCron) {
      elements.jobCron.addEventListener('input', debounce(validateCron, 300));
    }
    
    // Real-time JSON validation
    if (elements.jobPayload) {
      elements.jobPayload.addEventListener('input', debounce(validatePayload, 300));
    }
    
    // Action buttons
    if (elements.createRunBtn) {
      elements.createRunBtn.addEventListener('click', function() {
        handleFormSubmit(null, true);
      });
    }
    if (elements.runNowBtn) {
      elements.runNowBtn.addEventListener('click', runJobNow);
    }
    if (elements.deleteBtn) {
      elements.deleteBtn.addEventListener('click', openDeleteModal);
    }
    
    // Delete modal events
    if (elements.deleteModalClose) {
      elements.deleteModalClose.addEventListener('click', closeDeleteModal);
    }
    if (elements.deleteCancelBtn) {
      elements.deleteCancelBtn.addEventListener('click', closeDeleteModal);
    }
    if (elements.deleteConfirmBtn) {
      elements.deleteConfirmBtn.addEventListener('click', confirmDelete);
    }
    if (elements.deleteModal) {
      elements.deleteModal.addEventListener('click', function(e) {
        if (e.target.classList.contains('modal-overlay')) {
          closeDeleteModal();
        }
      });
    }
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        if (elements.deleteModal && elements.deleteModal.style.display !== 'none') {
          closeDeleteModal();
        } else if (elements.modal && elements.modal.style.display !== 'none') {
          closeModal();
        }
      }
    });
  }

  /**
   * Load scheduled jobs from API
   */
  function loadJobs() {
    showLoading();
    
    Auth.fetchWithAuth('/api/v1/admin/scheduled-jobs')
      .then(function(response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      })
      .then(function(data) {
        jobs = data.items || data || [];
        renderJobs();
        hideLoading();
      })
      .catch(function(err) {
        showError('Failed to load scheduled jobs: ' + err.message);
        hideLoading();
      });
  }

  /**
   * Render the jobs table
   */
  function renderJobs() {
    if (jobs.length === 0) {
      elements.jobsContainer.style.display = 'block';
      elements.jobsTable.style.display = 'none';
      elements.emptyState.style.display = 'block';
      return;
    }
    
    elements.jobsContainer.style.display = 'block';
    elements.jobsTable.style.display = 'table';
    elements.emptyState.style.display = 'none';
    
    // Build headers
    var headers = ['Name', 'Description', 'Cron', 'Enabled', 'Actions'];
    var headerHtml = '<tr>';
    for (var i = 0; i < headers.length; i++) {
      headerHtml += '<th>' + escapeHtml(headers[i]) + '</th>';
    }
    headerHtml += '</tr>';
    elements.tableHead.innerHTML = headerHtml;
    
    // Build rows
    var bodyHtml = '';
    for (var j = 0; j < jobs.length; j++) {
      var job = jobs[j];
      bodyHtml += '<tr data-job-id="' + escapeHtml(job.id) + '">';
      bodyHtml += '<td>' + escapeHtml(job.name) + '</td>';
      bodyHtml += '<td>' + escapeHtml(job.description || '-') + '</td>';
      bodyHtml += '<td><code>' + escapeHtml(job.cron_expression) + '</code></td>';
      bodyHtml += '<td>' + (job.enabled ? '<span class="badge badge-success">Yes</span>' : '<span class="badge badge-secondary">No</span>') + '</td>';
      bodyHtml += '<td>';
      bodyHtml += '<button class="btn btn-sm btn-secondary" data-action="edit" data-job-id="' + escapeHtml(job.id) + '" data-job-name="' + escapeHtml(job.name) + '" data-job-description="' + escapeHtml(job.description || '') + '" data-job-cron="' + escapeHtml(job.cron_expression) + '" data-job-payload="' + escapeHtml(JSON.stringify(job.payload || {})) + '" data-job-enabled="' + job.enabled + '">Edit</button>';
      bodyHtml += ' <button class="btn btn-sm btn-primary" data-action="run" data-job-id="' + escapeHtml(job.id) + '" data-job-name="' + escapeHtml(job.name) + '" data-job-description="' + escapeHtml(job.description || '') + '" data-job-cron="' + escapeHtml(job.cron_expression) + '" data-job-payload="' + escapeHtml(JSON.stringify(job.payload || {})) + '" data-job-enabled="' + job.enabled + '">Run Now</button>';
      bodyHtml += '</td>';
      bodyHtml += '</tr>';
    }
    elements.tableBody.innerHTML = bodyHtml;
    
    // Bind action buttons
    var actionButtons = elements.tableBody.querySelectorAll('[data-action]');
    for (var k = 0; k < actionButtons.length; k++) {
      actionButtons[k].addEventListener('click', handleActionClick);
    }
  }

  /**
   * Handle table action button clicks
   */
  function handleActionClick(e) {
    var btn = e.target;
    var action = btn.getAttribute('data-action');
    var jobId = btn.getAttribute('data-job-id');
    var jobName = btn.getAttribute('data-job-name');
    var jobDescription = btn.getAttribute('data-job-description');
    var jobCron = btn.getAttribute('data-job-cron');
    var jobPayload = btn.getAttribute('data-job-payload');
    var jobEnabled = btn.getAttribute('data-job-enabled') === 'true';
    
    var job = {
      id: jobId,
      name: jobName,
      description: jobDescription,
      cron_expression: jobCron,
      payload: JSON.parse(jobPayload || '{}'),
      enabled: jobEnabled
    };
    
    if (action === 'edit') {
      openEditModal(job);
    } else if (action === 'run') {
      runJobById(jobId, jobName);
    }
  }

  /**
   * Open modal for creating a new job
   */
  function openCreateModal() {
    currentJobId = null;
    resetForm();
    elements.modalTitle.textContent = 'Create Scheduled Job';
    elements.modalFooterCreate.style.display = 'flex';
    elements.modalFooterEdit.style.display = 'none';
    elements.jobEnabled.checked = true;
    elements.modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
    elements.jobName.focus();
  }

  /**
   * Open modal for editing an existing job
   */
  function openEditModal(job) {
    currentJobId = job.id;
    resetForm();
    elements.modalTitle.textContent = 'Edit Scheduled Job';
    elements.modalFooterCreate.style.display = 'none';
    elements.modalFooterEdit.style.display = 'flex';
    
    // Populate form
    elements.jobId.value = job.id;
    elements.jobName.value = job.name || '';
    elements.jobDescription.value = job.description || '';
    elements.jobCron.value = job.cron_expression || '';
    elements.jobPayload.value = JSON.stringify(job.payload || {}, null, 2);
    elements.jobEnabled.checked = job.enabled;
    
    elements.modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
    
    // Trigger validation
    validateCron();
    validatePayload();
  }

  /**
   * Close the job modal
   */
  function closeModal() {
    elements.modal.style.display = 'none';
    document.body.style.overflow = '';
    resetForm();
  }

  /**
   * Reset the form to default state
   */
  function resetForm() {
    elements.jobForm.reset();
    elements.jobId.value = '';
    elements.jobPayload.value = '{}';
    elements.cronHelper.style.display = 'none';
    clearErrors();
  }

  /**
   * Clear all form errors
   */
  function clearErrors() {
    elements.nameError.textContent = '';
    elements.nameError.style.display = 'none';
    elements.cronError.textContent = '';
    elements.cronError.style.display = 'none';
    elements.payloadError.textContent = '';
    elements.payloadError.style.display = 'none';
  }

  /**
   * Validate the entire form
   */
  function validateForm() {
    var isValid = true;
    clearErrors();
    
    // Validate name
    var name = elements.jobName.value.trim();
    if (!name) {
      showFieldError('name', 'Name is required');
      isValid = false;
    } else if (name.length < 3) {
      showFieldError('name', 'Name must be at least 3 characters');
      isValid = false;
    } else if (name.length > 255) {
      showFieldError('name', 'Name must be less than 255 characters');
      isValid = false;
    }
    
    // Validate cron
    var cron = elements.jobCron.value.trim();
    if (!cron) {
      showFieldError('cron', 'Cron expression is required');
      isValid = false;
    } else if (!isValidCron(cron)) {
      showFieldError('cron', 'Invalid cron expression');
      isValid = false;
    }
    
    // Validate payload
    if (!validatePayload()) {
      isValid = false;
    }
    
    return isValid;
  }

  /**
   * Show field-specific error
   */
  function showFieldError(field, message) {
    var errorEl = document.getElementById(field + '-error');
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.style.display = 'block';
    }
  }

  /**
   * Handle form submission
   */
  function handleFormSubmit(e, runAfterCreate) {
    if (e) {
      e.preventDefault();
    }
    
    if (isSubmitting) {
      return;
    }
    
    if (!validateForm()) {
      return;
    }
    
    isSubmitting = true;
    setSubmitting(true);
    
    var body = {
      name: elements.jobName.value.trim(),
      description: elements.jobDescription.value.trim() || null,
      cron_expression: elements.jobCron.value.trim(),
      payload: JSON.parse(elements.jobPayload.value || '{}'),
      enabled: elements.jobEnabled.checked
    };
    
    var url = '/api/v1/admin/scheduled-jobs';
    var method = 'POST';
    
    if (currentJobId) {
      url += '/' + currentJobId;
      method = 'PATCH';
    }
    
    Auth.fetchWithAuth(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(function(response) {
        if (!response.ok) {
          return response.json().then(function(err) {
            throw new Error(formatError(err));
          });
        }
        return response.json();
      })
      .then(function(data) {
        var jobId = currentJobId || data.id;
        
        if (runAfterCreate && jobId) {
          return runJobById(jobId, body.name, true).then(function() {
            return data;
          });
        }
        
        return data;
      })
      .then(function(data) {
        showToast(currentJobId ? 'Job updated successfully' : 'Job created successfully', 'success');
        closeModal();
        loadJobs();
      })
      .catch(function(err) {
        showToast('Failed to save job: ' + err.message, 'error');
      })
      .finally(function() {
        isSubmitting = false;
        setSubmitting(false);
      });
  }

  /**
   * Run a job now by ID
   */
  function runJobNow() {
    if (!currentJobId) {
      return;
    }
    runJobById(currentJobId, elements.jobName.value);
  }

  /**
   * Run a job by ID
   */
  function runJobById(jobId, jobName, silent) {
    return Auth.fetchWithAuth('/api/v1/admin/scheduled-jobs/' + jobId + '/run-now', {
      method: 'POST'
    })
      .then(function(response) {
        if (!response.ok) {
          return response.json().then(function(err) {
            throw new Error(formatError(err));
          });
        }
        if (!silent) {
          showToast('Job "' + escapeHtml(jobName) + '" triggered successfully', 'success');
        }
        return response.json();
      })
      .catch(function(err) {
        if (!silent) {
          showToast('Failed to run job: ' + err.message, 'error');
        }
        throw err;
      });
  }

  /**
   * Open delete confirmation modal
   */
  function openDeleteModal() {
    if (!currentJobId) {
      return;
    }
    elements.deleteJobName.textContent = elements.jobName.value;
    elements.deleteModal.style.display = 'block';
  }

  /**
   * Close delete confirmation modal
   */
  function closeDeleteModal() {
    elements.deleteModal.style.display = 'none';
  }

  /**
   * Confirm and execute delete
   */
  function confirmDelete() {
    if (!currentJobId || isSubmitting) {
      return;
    }
    
    isSubmitting = true;
    
    Auth.fetchWithAuth('/api/v1/admin/scheduled-jobs/' + currentJobId, {
      method: 'DELETE'
    })
      .then(function(response) {
        if (!response.ok) {
          return response.json().then(function(err) {
            throw new Error(formatError(err));
          });
        }
        showToast('Job deleted successfully', 'success');
        closeDeleteModal();
        closeModal();
        loadJobs();
      })
      .catch(function(err) {
        showToast('Failed to delete job: ' + err.message, 'error');
      })
      .finally(function() {
        isSubmitting = false;
      });
  }

  /**
   * Set submitting state on buttons
   */
  function setSubmitting(submitting) {
    var buttons = [elements.submitBtn, elements.saveBtn, elements.createRunBtn, elements.runNowBtn, elements.deleteConfirmBtn];
    for (var i = 0; i < buttons.length; i++) {
      if (buttons[i]) {
        buttons[i].disabled = submitting;
      }
    }
  }

  /**
   * Validate cron expression and show helper
   */
  function validateCron() {
    var cron = elements.jobCron.value.trim();
    
    if (!cron) {
      elements.cronHelper.style.display = 'none';
      elements.cronError.textContent = '';
      elements.cronError.style.display = 'none';
      return;
    }
    
    if (!isValidCron(cron)) {
      elements.cronHelper.style.display = 'none';
      elements.cronError.textContent = 'Invalid cron expression';
      elements.cronError.style.display = 'block';
      return;
    }
    
    elements.cronError.textContent = '';
    elements.cronError.style.display = 'none';
    
    // Show helper
    elements.cronHelper.style.display = 'block';
    elements.cronStatus.innerHTML = '✅ Valid cron expression';
    elements.cronStatus.className = 'cron-status valid';
    
    // Show human-readable description
    var description = getCronDescription(cron);
    elements.cronHumanReadable.textContent = description ? 'Human-readable: ' + description : '';
    
    // Show next runs
    var nextRuns = getNextRuns(cron, 5);
    var runsHtml = '<strong>Next 5 runs:</strong><ul>';
    for (var i = 0; i < nextRuns.length; i++) {
      runsHtml += '<li>' + formatDateTime(nextRuns[i]) + '</li>';
    }
    runsHtml += '</ul>';
    elements.cronNextRuns.innerHTML = runsHtml;
  }

  /**
   * Validate JSON payload
   */
  function validatePayload() {
    var payload = elements.jobPayload.value.trim();
    
    if (!payload) {
      elements.payloadError.textContent = '';
      elements.payloadError.style.display = 'none';
      return true;
    }
    
    try {
      JSON.parse(payload);
      elements.payloadError.textContent = '';
      elements.payloadError.style.display = 'none';
      return true;
    } catch (e) {
      elements.payloadError.textContent = 'Invalid JSON: ' + e.message;
      elements.payloadError.style.display = 'block';
      return false;
    }
  }

  /**
   * Check if a cron expression is valid
   */
  function isValidCron(cron) {
    // Standard cron: minute hour day month dow
    // Supports: * / , - and numbers
    var parts = cron.trim().split(/\s+/);
    if (parts.length !== 5) {
      return false;
    }
    
    var ranges = [
      { min: 0, max: 59 },   // minute
      { min: 0, max: 23 },   // hour
      { min: 1, max: 31 },   // day of month
      { min: 1, max: 12 },   // month
      { min: 0, max: 7 }     // day of week (0-7, where 0 and 7 are Sunday)
    ];
    
    for (var i = 0; i < 5; i++) {
      if (!isValidCronField(parts[i], ranges[i].min, ranges[i].max)) {
        return false;
      }
    }
    
    return true;
  }

  /**
   * Validate a single cron field
   */
  function isValidCronField(field, min, max) {
    // Handle special characters
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
    
    // Handle ranges (e.g., 1-5)
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
    
    // Handle lists (e.g., 1,2,3)
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
    
    // Single value
    var singleVal = parseInt(field, 10);
    if (isNaN(singleVal)) {
      return false;
    }
    // Handle day of week 0 or 7 as Sunday
    if (min === 0 && max === 7 && singleVal === 7) {
      return true;
    }
    return singleVal >= min && singleVal <= max;
  }

  /**
   * Get human-readable description of a cron expression
   */
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

  /**
   * Calculate next run times for a cron expression
   */
  function getNextRuns(cron, count) {
    var parts = cron.trim().split(/\s+/);
    if (parts.length !== 5) {
      return [];
    }
    
    var runs = [];
    var now = new Date();
    var current = new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours(), now.getMinutes(), 0, 0);
    
    // Limit search to prevent infinite loops
    var maxIterations = count * 60 * 24 * 366; // Roughly a year of minutes
    var iterations = 0;
    
    while (runs.length < count && iterations < maxIterations) {
      current = new Date(current.getTime() + 60 * 1000); // Add 1 minute
      iterations++;
      
      if (matchesCron(current, parts)) {
        runs.push(new Date(current));
      }
    }
    
    return runs;
  }

  /**
   * Check if a date matches a cron expression
   */
  function matchesCron(date, parts) {
    var minute = date.getMinutes();
    var hour = date.getHours();
    var dom = date.getDate();
    var month = date.getMonth() + 1; // JavaScript months are 0-based
    var dow = date.getDay();
    
    return matchesCronField(minute, parts[0], 0, 59) &&
           matchesCronField(hour, parts[1], 0, 23) &&
           matchesCronField(dom, parts[2], 1, 31) &&
           matchesCronField(month, parts[3], 1, 12) &&
           matchesCronField(dow, parts[4], 0, 7);
  }

  /**
   * Check if a value matches a cron field
   */
  function matchesCronField(value, field, min, max) {
    // Handle * (any)
    if (field === '*') {
      return true;
    }
    
    // Handle step values (e.g., */5)
    if (field.indexOf('/') !== -1) {
      var stepParts = field.split('/');
      var base = stepParts[0];
      var step = parseInt(stepParts[1], 10);
      
      if (base === '*') {
        return (value - min) % step === 0;
      }
      
      // Handle ranges with step (e.g., 1-10/2)
      if (base.indexOf('-') !== -1) {
        var rangeParts = base.split('-');
        var start = parseInt(rangeParts[0], 10);
        return value >= start && (value - start) % step === 0;
      }
      
      return false;
    }
    
    // Handle ranges (e.g., 1-5)
    if (field.indexOf('-') !== -1) {
      var rangeParts = field.split('-');
      var start = parseInt(rangeParts[0], 10);
      var end = parseInt(rangeParts[1], 10);
      return value >= start && value <= end;
    }
    
    // Handle lists (e.g., 1,2,3)
    if (field.indexOf(',') !== -1) {
      var values = field.split(',');
      for (var i = 0; i < values.length; i++) {
        if (parseInt(values[i], 10) === value) {
          return true;
        }
      }
      return false;
    }
    
    // Single value
    var fieldVal = parseInt(field, 10);
    // Handle day of week 0 or 7 as Sunday
    if (min === 0 && max === 7 && fieldVal === 7 && value === 0) {
      return true;
    }
    return fieldVal === value;
  }

  /**
   * Format time as HH:MM AM/PM
   */
  function formatTime(hour, minute) {
    var period = hour >= 12 ? 'PM' : 'AM';
    var displayHour = hour % 12;
    if (displayHour === 0) {
      displayHour = 12;
    }
    var displayMinute = minute < 10 ? '0' + minute : minute;
    return displayHour + ':' + displayMinute + ' ' + period;
  }

  /**
   * Format date and time
   */
  function formatDateTime(date) {
    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var month = months[date.getMonth()];
    var day = date.getDate();
    var year = date.getFullYear();
    var time = formatTime(date.getHours(), date.getMinutes());
    return month + ' ' + day + ', ' + year + ' at ' + time;
  }

  /**
   * Show toast notification
   */
  function showToast(message, type) {
    if (!elements.toastContainer) {
      return;
    }
    
    var toast = document.createElement('div');
    toast.className = 'toast ' + (type || 'info');
    toast.textContent = message;
    
    elements.toastContainer.appendChild(toast);
    
    // Auto-remove after 4 seconds
    setTimeout(function() {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'opacity 0.3s, transform 0.3s';
      setTimeout(function() {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 4000);
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

  /**
   * Show loading state
   */
  function showLoading() {
    if (elements.loading) {
      elements.loading.style.display = 'block';
    }
    if (elements.jobsContainer) {
      elements.jobsContainer.style.display = 'none';
    }
    if (elements.error) {
      elements.error.style.display = 'none';
    }
  }

  /**
   * Hide loading state
   */
  function hideLoading() {
    if (elements.loading) {
      elements.loading.style.display = 'none';
    }
  }

  /**
   * Show error message
   */
  function showError(message) {
    if (elements.error) {
      elements.error.textContent = message;
      elements.error.style.display = 'block';
    }
    hideLoading();
  }

  /**
   * Format error response
   */
  function formatError(err) {
    if (err.detail) {
      if (Array.isArray(err.detail)) {
        return err.detail.map(function(e) {
          return (e.loc ? e.loc.join('.') + ': ' : '') + e.msg;
        }).join('; ');
      }
      if (typeof err.detail === 'string') {
        return err.detail;
      }
      return JSON.stringify(err.detail);
    }
    return err.message || JSON.stringify(err);
  }

  /**
   * Escape HTML special characters
   */
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

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
