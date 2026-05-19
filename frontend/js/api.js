// ============================================================
// api.js — Backend API bilan muloqot qatlami
// ============================================================

const API_BASE = 'http://localhost:8000/api/v1';

const Api = {
  // ── Token boshqaruvi ──────────────────────
  getToken:   () => localStorage.getItem('token'),
  getUser:    () => { try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch { return {}; } },
  setSession: (token, user) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
  },
  clearSession: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  },

  // ── Asosiy so'rov funksiyasi ──────────────
  async request(method, path, body = null, isForm = false) {
    const headers = {};
    const token = this.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let requestBody;
    if (isForm) {
      requestBody = body;
    } else if (body !== null) {
      headers['Content-Type'] = 'application/json';
      requestBody = JSON.stringify(body);
    }

    let res;
    try {
      res = await fetch(`${API_BASE}${path}`, { method, headers, body: requestBody });
    } catch {
      throw new Error('Server bilan ulanishda xatolik. Uvicorn ishlayaptimi?');
    }

    if (res.status === 401) {
      this.clearSession();
      window.location.href = 'login.html';
      return;
    }

    let data;
    try { data = await res.json(); } catch { data = {}; }

    if (!res.ok) {
      const msg = typeof data.detail === 'string' ? data.detail
        : Array.isArray(data.detail) ? data.detail.map(d => d.msg).join(', ')
        : JSON.stringify(data.detail || 'Xatolik');
      throw new Error(msg);
    }
    return data;
  },

  get:    (path)        => Api.request('GET',    path),
  post:   (path, body)  => Api.request('POST',   path, body),
  put:    (path, body)  => Api.request('PUT',    path, body),
  delete: (path)        => Api.request('DELETE', path),

  // ── Auth ──────────────────────────────────
  login(username, password) {
    const form = new URLSearchParams();
    form.append('username', username);
    form.append('password', password);
    return Api.request('POST', '/auth/login', form, true);
  },
  me: () => Api.get('/auth/me'),

  // ── Mahsulotlar ───────────────────────────
  products: {
    list: (page = 1, size = 50, q = '') =>
      Api.get(`/products/?page=${page}&size=${size}${q ? `&kiyim_nomi=${encodeURIComponent(q)}` : ''}`),
    create:  (data) => Api.post('/products/', data),
    update:  (id, data) => Api.put(`/products/${id}`, data),
    delete:  (id) => Api.delete(`/products/${id}`),
    search:  (code) => Api.get(`/products/search?shtrix_kod=${encodeURIComponent(code.trim())}`),
    detail:  (id) => Api.get(`/products/${id}`),
  },

  // ── Ombor ─────────────────────────────────
  inventory: {
    list:     (page = 1, size = 100) => Api.get(`/inventory/?page=${page}&size=${size}`),
    addStock: (data)     => Api.post('/inventory/add-stock', data),
    lowStock: (limit = 5) => Api.get(`/inventory/low-stock?chegara=${limit}`),
    detail:   (productId) => Api.get(`/inventory/${productId}`),
  },

  // ── Mijozlar ──────────────────────────────
  customers: {
    list:   (page = 1, size = 50, q = '') =>
      Api.get(`/customers/?page=${page}&size=${size}${q ? `&qidiruv=${encodeURIComponent(q)}` : ''}`),
    create: (data)      => Api.post('/customers/', data),
    update: (id, data)  => Api.put(`/customers/${id}`, data),
    detail: (id)        => Api.get(`/customers/${id}`),
  },

  // ── Fakturalar ────────────────────────────
  invoices: {
    list:   (page = 1, size = 50, statusFilter = '') =>
      Api.get(`/invoices/?page=${page}&size=${size}${statusFilter ? `&status=${statusFilter}` : ''}`),
    create: (data)  => Api.post('/invoices/', data),
    detail: (id)    => Api.get(`/invoices/${id}`),
    cancel: (id)    => Api.put(`/invoices/${id}/cancel`),
    status: (id, s) => Api.put(`/invoices/${id}/status`, { status: s }),
  },
};
