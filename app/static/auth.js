(function () {
  function getToken() {
    return (
      localStorage.getItem('brainapi.authToken') ||
      sessionStorage.getItem('brainapi.authToken') ||
      localStorage.getItem('authToken') ||
      sessionStorage.getItem('authToken') ||
      ''
    );
  }

  function storeToken(token, options) {
    const rememberMe = Boolean(options && options.rememberMe);
    const user = options && options.user ? options.user : null;
    const storage = rememberMe ? localStorage : sessionStorage;
    const otherStorage = rememberMe ? sessionStorage : localStorage;

    storage.setItem('brainapi.authToken', token);
    storage.setItem('authToken', token);
    otherStorage.removeItem('brainapi.authToken');
    otherStorage.removeItem('authToken');

    if (user && user.email) {
      storage.setItem('userEmail', user.email);
    }

    if (user && user.name) {
      storage.setItem('brainapi.userName', user.name);
    }
  }

  function clearToken() {
    localStorage.removeItem('brainapi.authToken');
    sessionStorage.removeItem('brainapi.authToken');
    localStorage.removeItem('authToken');
    sessionStorage.removeItem('authToken');
  }

  function friendlyErrorMessage(message, statusCode) {
    const msg = String(message || '').toLowerCase();

    if (msg.includes('quota') || msg.includes('billing') || msg.includes('insufficient_quota') || statusCode === 402) {
      return 'Quota exceeded or billing issue. Please upgrade or check your plan.';
    }
    if (msg.includes('invalid') || msg.includes('unauthorized') || msg.includes('expired') || statusCode === 401 || statusCode === 403) {
      return 'Authentication failed. Please check your credentials and try again.';
    }
    if (msg.includes('network') || msg.includes('failed to fetch') || statusCode === 503) {
      return 'Network issue detected. Please try again.';
    }
    if (statusCode >= 500) {
      return 'Something went wrong. Please try again in a moment.';
    }
    return 'Request failed. Please try again.';
  }

  async function postJson(path, payload) {
    const response = await fetch(path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    const text = await response.text();
    let data = {};

    if (text) {
      try {
        data = JSON.parse(text);
      } catch (error) {
        data = { detail: text };
      }
    }

    if (!response.ok) {
      throw new Error(friendlyErrorMessage(data.detail || data.message || '', response.status));
    }

    return data;
  }

  window.BrainAPIAuth = {
    clearToken: clearToken,
    getToken: getToken,
    postJson: postJson,
    storeToken: storeToken
  };
})();