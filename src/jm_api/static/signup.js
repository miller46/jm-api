/**
 * Signup page functionality
 * Handles form validation, password strength, and API integration
 */

(function() {
  'use strict';

  // Form elements
  var form = document.getElementById('signup-form');
  var emailInput = document.getElementById('email');
  var passwordInput = document.getElementById('password');
  var confirmPasswordInput = document.getElementById('confirm-password');
  var submitBtn = document.getElementById('submit-btn');
  var toastContainer = document.getElementById('toast-container');

  // Field error elements
  var emailError = document.getElementById('email-error');
  var passwordError = document.getElementById('password-error');
  var confirmPasswordError = document.getElementById('confirm-password-error');
  var passwordStrengthBar = document.getElementById('password-strength-bar');
  var passwordStrengthText = document.getElementById('password-strength-text');

  // Validation state
  var validationState = {
    email: false,
    password: false,
    confirmPassword: false
  };

  /**
   * Check if user is already authenticated and redirect if so
   */
  function checkAuth() {
    var token = localStorage.getItem('access_token');
    if (token) {
      // Verify token is valid by calling /me endpoint
      fetch('/api/v1/auth/me', {
        headers: {
          'Authorization': 'Bearer ' + token
        }
      })
      .then(function(response) {
        if (response.ok) {
          // User is authenticated, redirect to dashboard
          window.location.href = '/admin/';
        } else {
          // Token is invalid, clear it
          localStorage.removeItem('access_token');
        }
      })
      .catch(function() {
        // Error checking auth, clear token
        localStorage.removeItem('access_token');
      });
    }
  }

  /**
   * Show a toast notification
   */
  function showToast(message, type) {
    type = type || 'error';
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    // Remove after 5 seconds
    setTimeout(function() {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(function() {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 5000);
  }

  /**
   * Show field error
   */
  function showFieldError(input, errorEl, show) {
    if (show) {
      input.classList.add('error');
      errorEl.classList.add('visible');
    } else {
      input.classList.remove('error');
      errorEl.classList.remove('visible');
    }
  }

  /**
   * Validate email format
   */
  function isValidEmail(email) {
    var emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  /**
   * Calculate password strength
   * Returns: 0 (weak), 1 (medium), 2 (strong)
   */
  function calculatePasswordStrength(password) {
    var strength = 0;
    
    if (password.length >= 8) strength++;
    if (password.length >= 12) strength++;
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength++;
    if (/\d/.test(password)) strength++;
    if (/[^a-zA-Z0-9]/.test(password)) strength++;

    if (strength <= 2) return 0; // weak
    if (strength <= 4) return 1; // medium
    return 2; // strong
  }

  /**
   * Update password strength indicator
   */
  function updatePasswordStrength(password) {
    var strength = calculatePasswordStrength(password);
    
    passwordStrengthBar.className = 'password-strength-bar';
    
    if (password.length === 0) {
      passwordStrengthText.textContent = '';
      return;
    }

    if (strength === 0) {
      passwordStrengthBar.classList.add('weak');
      passwordStrengthText.textContent = 'Weak password';
      passwordStrengthText.style.color = '#dc3545';
    } else if (strength === 1) {
      passwordStrengthBar.classList.add('medium');
      passwordStrengthText.textContent = 'Medium strength';
      passwordStrengthText.style.color = '#ffc107';
    } else {
      passwordStrengthBar.classList.add('strong');
      passwordStrengthText.textContent = 'Strong password';
      passwordStrengthText.style.color = '#28a745';
    }
  }

  /**
   * Validate password requirements
   */
  function isValidPassword(password) {
    // At least 8 characters
    if (password.length < 8) return false;
    // At least one uppercase
    if (!/[A-Z]/.test(password)) return false;
    // At least one lowercase
    if (!/[a-z]/.test(password)) return false;
    // At least one number
    if (!/\d/.test(password)) return false;
    
    return true;
  }

  /**
   * Validate email field
   */
  function validateEmail() {
    var email = emailInput.value.trim();
    var isValid = isValidEmail(email);
    showFieldError(emailInput, emailError, !isValid && email.length > 0);
    validationState.email = isValid;
    return isValid;
  }

  /**
   * Validate password field
   */
  function validatePassword() {
    var password = passwordInput.value;
    var isValid = isValidPassword(password);
    showFieldError(passwordInput, passwordError, !isValid && password.length > 0);
    validationState.password = isValid;
    return isValid;
  }

  /**
   * Validate confirm password field
   */
  function validateConfirmPassword() {
    var password = passwordInput.value;
    var confirmPassword = confirmPasswordInput.value;
    var isValid = password === confirmPassword && confirmPassword.length > 0;
    showFieldError(confirmPasswordInput, confirmPasswordError, !isValid && confirmPassword.length > 0);
    validationState.confirmPassword = isValid;
    return isValid;
  }

  /**
   * Validate entire form
   */
  function validateForm() {
    var emailValid = validateEmail();
    var passwordValid = validatePassword();
    var confirmValid = validateConfirmPassword();
    
    return emailValid && passwordValid && confirmValid;
  }

  /**
   * Set loading state on submit button
   */
  function setLoading(loading) {
    if (loading) {
      submitBtn.disabled = true;
      submitBtn.classList.add('loading');
    } else {
      submitBtn.disabled = false;
      submitBtn.classList.remove('loading');
    }
  }

  /**
   * Handle signup API call
   */
  function handleSignup(email, password) {
    setLoading(true);

    fetch('/api/v1/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        email: email,
        password: password,
        is_admin: false
      })
    })
    .then(function(response) {
      setLoading(false);

      if (response.status === 201) {
        // Success
        return response.json().then(function(data) {
          showToast('Account created successfully! Redirecting to login...', 'success');
          
          // Redirect to login page after a short delay
          setTimeout(function() {
            window.location.href = '/admin/login';
          }, 2000);
        });
      } else if (response.status === 409) {
        // Email already exists
        showToast('An account with this email already exists.', 'error');
        emailInput.classList.add('error');
      } else if (response.status === 422) {
        // Validation error
        return response.json().then(function(data) {
          var detail = data.detail;
          if (Array.isArray(detail)) {
            var messages = detail.map(function(err) {
              return err.msg;
            }).join('; ');
            showToast('Validation error: ' + messages, 'error');
          } else {
            showToast('Please check your input and try again.', 'error');
          }
        });
      } else if (response.status === 429) {
        // Rate limited
        showToast('Too many signup attempts. Please try again later.', 'error');
      } else {
        // Other error
        showToast('An error occurred. Please try again.', 'error');
      }
    })
    .catch(function(error) {
      setLoading(false);
      showToast('Network error. Please check your connection and try again.', 'error');
      console.error('Signup error:', error);
    });
  }

  /**
   * Handle form submission
   */
  function handleSubmit(event) {
    event.preventDefault();

    // Clear any existing errors
    showFieldError(emailInput, emailError, false);
    showFieldError(passwordInput, passwordError, false);
    showFieldError(confirmPasswordInput, confirmPasswordError, false);

    // Validate form
    if (!validateForm()) {
      // Show specific errors for empty fields
      if (!emailInput.value.trim()) {
        showFieldError(emailInput, emailError, true);
      }
      if (!passwordInput.value) {
        showFieldError(passwordInput, passwordError, true);
      }
      if (!confirmPasswordInput.value) {
        showFieldError(confirmPasswordInput, confirmPasswordError, true);
      }
      return;
    }

    // Check if passwords match one more time
    if (passwordInput.value !== confirmPasswordInput.value) {
      showFieldError(confirmPasswordInput, confirmPasswordError, true);
      showToast('Passwords do not match', 'error');
      return;
    }

    // Submit signup
    handleSignup(emailInput.value.trim(), passwordInput.value);
  }

  /**
   * Create a login.html placeholder if it doesn't exist
   * (This is just a fallback - the actual login page should be implemented separately)
   */
  function ensureLoginPageExists() {
    // The login link points to /admin/login which should be handled by the backend
    // or another static file. For now, we assume it exists.
  }

  // Initialize
  document.addEventListener('DOMContentLoaded', function() {
    // Check if already authenticated
    checkAuth();

    // Add event listeners
    emailInput.addEventListener('blur', validateEmail);
    emailInput.addEventListener('input', function() {
      if (emailInput.classList.contains('error')) {
        validateEmail();
      }
    });

    passwordInput.addEventListener('input', function() {
      updatePasswordStrength(passwordInput.value);
      if (passwordInput.classList.contains('error')) {
        validatePassword();
      }
      // Also validate confirm password if it has a value
      if (confirmPasswordInput.value) {
        validateConfirmPassword();
      }
    });

    passwordInput.addEventListener('blur', validatePassword);

    confirmPasswordInput.addEventListener('input', function() {
      if (confirmPasswordInput.classList.contains('error')) {
        validateConfirmPassword();
      }
    });

    confirmPasswordInput.addEventListener('blur', validateConfirmPassword);

    form.addEventListener('submit', handleSubmit);
  });
})();
