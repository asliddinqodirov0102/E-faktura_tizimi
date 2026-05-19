// app.js - Asosiy mantiq
document.addEventListener('DOMContentLoaded', init);

const state = {
  currentPage: 'dashboard',
  cart: [],
  user: null,
};

function init() {
  const token = Api.getToken();
  if (!token) {
    window.location.href = 'login.html';
    return;
  }
  state.user = Api.getUser();
  document.getElementById('userName').textContent = state.user.ism_sharif || state.user.login || 'Foydalanuvchi';
  document.getElementById('userRole').textContent = state.user.rol || 'Xodim';

  lucide.createIcons();

  document.getElementById('logoutBtn').addEventListener('click', () => {
    Api.clearSession();
    window.location.href = 'login.html';
  });

  document.getElementById('modalClose').addEventListener('click', closeModal);

  // Sidebar navigation
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      el.classList.add('active');
      loadPage(el.dataset.page);
    });
  });

  loadPage('dashboard');
}

async function loadPage(page) {
  state.currentPage = page;
  const content = document.getElementById('pageContent');
  const title = document.getElementById('pageTitle');
  const actions = document.getElementById('headerActions');
  
  content.innerHTML = '<div class="loading-state"><div class="spinner"></div><span>Yuklanmoqda...</span></div>';
  actions.innerHTML = '';

  try {
    switch (page) {
      case 'dashboard':
        title.textContent = 'Dashboard';
        await renderDashboard(content);
        break;
      case 'products':
        title.textContent = 'Mahsulotlar';
        if (['admin', 'omborchi'].includes(state.user.rol)) {
          actions.innerHTML = `<button class="btn btn-primary" onclick="openProductModal()"><i data-lucide="plus"></i> Yangi qo'shish</button>`;
        }
        await renderProducts(content);
        break;
      case 'inventory':
        title.textContent = 'Ombor';
        if (['admin', 'omborchi'].includes(state.user.rol)) {
          actions.innerHTML = `<button class="btn btn-success" onclick="openAddStockModal()"><i data-lucide="download"></i> Kirim qilish</button>`;
        }
        await renderInventory(content);
        break;
      case 'customers':
        title.textContent = 'Mijozlar';
        actions.innerHTML = `<button class="btn btn-primary" onclick="openCustomerModal()"><i data-lucide="user-plus"></i> Mijoz qo'shish</button>`;
        await renderCustomers(content);
        break;
      case 'sell':
        title.textContent = 'Sotuv (Kassa)';
        await renderSell(content);
        break;
      case 'invoices':
        title.textContent = 'Fakturalar ro\'yxati';
        await renderInvoices(content);
        break;
    }
    lucide.createIcons();
  } catch (err) {
    content.innerHTML = `<div class="empty-state"><p class="toast-error" style="padding:10px">${err.message}</p></div>`;
  }
}

// ==========================================
// TOAST NOTIFICATIONS
// ==========================================
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ==========================================
// MODAL LOGIC
// ==========================================
function openModal(title, bodyHtml, footerHtml, isLarge = false) {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalBody').innerHTML = bodyHtml;
  document.getElementById('modalFooter').innerHTML = footerHtml;
  const box = document.getElementById('modalBox');
  if (isLarge) box.classList.add('modal-lg'); else box.classList.remove('modal-lg');
  document.getElementById('modalOverlay').classList.add('open');
}
function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
}

// ==========================================
// PAGES
// ==========================================

async function renderDashboard(container) {
  try {
    const products = await Api.products.list(1, 1);
    const customers = await Api.customers.list(1, 1);
    const lowStock = await Api.inventory.lowStock(5);
    
    container.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">Jami Mahsulotlar</div>
          <div class="stat-value">${products.total || 0}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Jami Mijozlar</div>
          <div class="stat-value">${customers.total || 0}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Kam qolgan tovarlar</div>
          <div class="stat-value" style="color:var(--yellow)">${lowStock.items.length || 0}</div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header"><div class="panel-title">Kam qolgan tovarlar ro'yxati (Top 10)</div></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Nomi</th><th>Shtrix kod</th><th>Qoldiq</th></tr></thead>
            <tbody>
              ${lowStock.items.slice(0, 10).map(s => `<tr><td>${s.kiyim_nomi}</td><td>${s.shtrix_kod}</td><td style="color:var(--yellow);font-weight:bold">${s.mavjud_miqdor} ta</td></tr>`).join('') || '<tr><td colspan="3" style="text-align:center">Hammasi joyida</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Xatolik: ${err.message}</div>`;
  }
}

async function renderProducts(container) {
  const data = await Api.products.list(1, 50);
  
  let rows = '';
  data.items.forEach(p => {
    rows += `<tr>
      <td>${p.kiyim_nomi}</td>
      <td><span class="badge badge-gray">${p.shtrix_kod}</span></td>
      <td>${p.razmer}</td>
      <td>${p.rang}</td>
      <td>${p.sotilish_narxi} so'm</td>
    </tr>`;
  });

  container.innerHTML = `
    <div class="panel">
      <div class="table-wrap">
        <table>
          <thead><tr><th>Nomi</th><th>Shtrix kod</th><th>Razmer</th><th>Rang</th><th>Narx</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function openProductModal() {
  const body = `
    <div class="form-group"><label class="form-label">Kiyim nomi</label><input type="text" id="p_nomi" class="form-input"></div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Shtrix kod</label><input type="text" id="p_kod" class="form-input"></div>
      <div class="form-group"><label class="form-label">Razmer</label><input type="text" id="p_razmer" class="form-input"></div>
    </div>
    <div class="form-row">
      <div class="form-group"><label class="form-label">Rang</label><input type="text" id="p_rang" class="form-input"></div>
      <div class="form-group"><label class="form-label">Sotuv narxi</label><input type="number" id="p_narx" class="form-input"></div>
    </div>
  `;
  const footer = `
    <button class="btn btn-ghost" onclick="closeModal()">Bekor qilish</button>
    <button class="btn btn-primary" onclick="saveProduct()">Saqlash</button>
  `;
  openModal('Yangi mahsulot', body, footer);
}

window.saveProduct = async function() {
  try {
    await Api.products.create({
      kiyim_nomi: document.getElementById('p_nomi').value,
      shtrix_kod: document.getElementById('p_kod').value,
      razmer: document.getElementById('p_razmer').value,
      rang: document.getElementById('p_rang').value,
      kelgan_narxi: 0,
      sotilish_narxi: parseFloat(document.getElementById('p_narx').value) || 0
    });
    showToast('Mahsulot qo\'shildi');
    closeModal();
    loadPage('products');
  } catch(e) { showToast(e.message, 'error'); }
}

async function renderInventory(container) {
  const data = await Api.inventory.list(1, 50);
  let rows = '';
  data.items.forEach(i => {
    rows += `<tr>
      <td>${i.product.kiyim_nomi}</td>
      <td><span class="badge badge-gray">${i.product.shtrix_kod}</span></td>
      <td><strong>${i.miqdor}</strong> ta</td>
    </tr>`;
  });
  container.innerHTML = `<div class="panel"><div class="table-wrap"><table><thead><tr><th>Mahsulot</th><th>Shtrix kod</th><th>Qoldiq</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

function openAddStockModal() {
  const body = `
    <div class="form-group"><label class="form-label">Shtrix kod (Product)</label><input type="text" id="s_kod" class="form-input" onchange="lookupProductForStock()"></div>
    <div id="s_prod_info" style="margin-bottom:15px;color:var(--green)"></div>
    <div class="form-group"><label class="form-label">Qo'shiladigan miqdor</label><input type="number" id="s_qty" class="form-input" value="1"></div>
  `;
  const footer = `
    <button class="btn btn-ghost" onclick="closeModal()">Bekor qilish</button>
    <button class="btn btn-success" onclick="saveStock()">Kirim qilish</button>
  `;
  openModal('Omborga kirim qilish', body, footer);
}

let stockSelectedProductId = null;
window.lookupProductForStock = async function() {
  const code = document.getElementById('s_kod').value;
  try {
    const prod = await Api.products.search(code);
    document.getElementById('s_prod_info').textContent = `Topildi: ${prod.kiyim_nomi} (${prod.razmer}, ${prod.rang})`;
    stockSelectedProductId = prod.id;
  } catch(e) {
    document.getElementById('s_prod_info').innerHTML = `<span class="toast-error">Topilmadi</span>`;
    stockSelectedProductId = null;
  }
}

window.saveStock = async function() {
  if (!stockSelectedProductId) return showToast('Mahsulotni tanlang', 'error');
  try {
    await Api.inventory.addStock({
      product_id: stockSelectedProductId,
      qoshiladigan_miqdor: parseInt(document.getElementById('s_qty').value) || 0
    });
    showToast('Kirim qilindi');
    closeModal();
    loadPage('inventory');
  } catch(e) { showToast(e.message, 'error'); }
}

async function renderCustomers(container) {
  const data = await Api.customers.list(1, 50);
  let rows = '';
  data.items.forEach(c => {
    rows += `<tr>
      <td>${c.ism_sharif}</td>
      <td>${c.telefon || '-'}</td>
      <td><span class="badge badge-gray">${c.mijoz_turi}</span></td>
    </tr>`;
  });
  container.innerHTML = `<div class="panel"><div class="table-wrap"><table><thead><tr><th>Mijoz</th><th>Telefon</th><th>Turi</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

function openCustomerModal() {
  const body = `
    <div class="form-group"><label class="form-label">Ism sharif</label><input type="text" id="c_ism" class="form-input"></div>
    <div class="form-group"><label class="form-label">Telefon</label><input type="text" id="c_tel" class="form-input"></div>
    <div class="form-group"><label class="form-label">Turi</label>
      <select id="c_turi" class="form-select"><option value="jismoniy">Jismoniy shaxs</option><option value="yuridik">Yuridik shaxs</option></select>
    </div>
  `;
  const footer = `
    <button class="btn btn-ghost" onclick="closeModal()">Bekor qilish</button>
    <button class="btn btn-primary" onclick="saveCustomer()">Saqlash</button>
  `;
  openModal('Yangi mijoz', body, footer);
}

window.saveCustomer = async function() {
  try {
    await Api.customers.create({
      ism_sharif: document.getElementById('c_ism').value,
      telefon: document.getElementById('c_tel').value,
      mijoz_turi: document.getElementById('c_turi').value
    });
    showToast('Mijoz qo\'shildi');
    closeModal();
    loadPage('customers');
  } catch(e) { showToast(e.message, 'error'); }
}

// ==========================================
// SELL PAGE
// ==========================================
async function renderSell(container) {
  state.cart = [];
  container.innerHTML = `
    <div class="sell-layout">
      <div class="sell-left">
        <div class="panel">
          <div class="panel-header"><div class="panel-title">Mijoz tanlash</div></div>
          <div class="panel-body">
            <div class="search-wrap" style="width:100%"><i data-lucide="search"></i><input type="text" id="sell_cust" class="search-input" style="width:100%" placeholder="Tel raqam kiritib Enter bosing..." onchange="searchCustomerForSell()"></div>
            <div id="sell_cust_info" style="margin-top:10px;font-weight:bold;color:var(--green)">Mijoz tanlanmagan (Umumiy xaridor)</div>
          </div>
        </div>
        <div class="panel" style="flex:1">
          <div class="panel-header"><div class="panel-title">Mahsulot qidirish (Shtrix kod)</div></div>
          <div class="panel-body">
            <div class="search-wrap" style="width:100%"><i data-lucide="barcode"></i><input type="text" id="sell_barcode" class="search-input" style="width:100%" placeholder="Shtrix kod skanerlang..." onchange="addProdToCart()"></div>
          </div>
        </div>
      </div>
      <div class="sell-right">
        <div class="panel cart-panel">
          <div class="panel-header"><div class="panel-title">Savat</div></div>
          <div class="panel-body" style="display:flex;flex-direction:column;height:100%">
            <div class="cart-items" id="cart_items">Savatcha bo'sh</div>
            <div class="cart-total">
              <div class="cart-total-row"><span class="cart-total-label">Jami:</span><span class="cart-total-amount" id="cart_total_sum">0 so'm</span></div>
              <button class="btn btn-primary" style="width:100%;margin-top:10px;justify-content:center" onclick="completeSale()">Sotish / Faktura yaratish</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

let sellSelectedCustomer = null;
window.searchCustomerForSell = async function() {
  const q = document.getElementById('sell_cust').value;
  try {
    const res = await Api.customers.list(1, 1, q);
    if(res.items.length > 0) {
      sellSelectedCustomer = res.items[0];
      document.getElementById('sell_cust_info').textContent = `Tanlandi: ${sellSelectedCustomer.ism_sharif}`;
    } else {
      document.getElementById('sell_cust_info').innerHTML = `<span style="color:var(--red)">Topilmadi</span>`;
      sellSelectedCustomer = null;
    }
  } catch(e) {
    document.getElementById('sell_cust_info').innerHTML = `<span style="color:var(--red)">Xato: ${e.message}</span>`;
  }
}

window.addProdToCart = async function() {
  const input = document.getElementById('sell_barcode');
  const code = input.value.trim();
  input.value = '';
  if(!code) return;

  try {
    const prod = await Api.products.search(code);
    const existing = state.cart.find(c => c.product_id === prod.id);
    if(existing) {
      existing.miqdor += 1;
    } else {
      state.cart.push({
        product_id: prod.id,
        nomi: prod.kiyim_nomi,
        narxi: prod.sotilish_narxi,
        miqdor: 1
      });
    }
    renderCart();
  } catch(e) {
    showToast(`Bunday shtrix-kod topilmadi: ${code}`, 'error');
  }
}

function renderCart() {
  const container = document.getElementById('cart_items');
  let total = 0;
  if(state.cart.length === 0) {
    container.innerHTML = "Savatcha bo'sh";
    document.getElementById('cart_total_sum').textContent = "0 so'm";
    return;
  }

  let html = '';
  state.cart.forEach((c, idx) => {
    const sum = c.miqdor * c.narxi;
    total += sum;
    html += `
      <div class="cart-item">
        <div class="cart-item-info">
          <div class="cart-item-name">${c.nomi}</div>
          <div class="cart-item-price">${c.narxi} so'm</div>
        </div>
        <div class="cart-qty">
          <button class="qty-btn" onclick="updateCartQty(${idx}, -1)">-</button>
          <div class="qty-val">${c.miqdor}</div>
          <button class="qty-btn" onclick="updateCartQty(${idx}, 1)">+</button>
        </div>
        <div class="cart-item-total">${sum} so'm</div>
      </div>
    `;
  });
  container.innerHTML = html;
  document.getElementById('cart_total_sum').textContent = `${total} so'm`;
}

window.updateCartQty = function(idx, delta) {
  state.cart[idx].miqdor += delta;
  if(state.cart[idx].miqdor <= 0) {
    state.cart.splice(idx, 1);
  }
  renderCart();
}

window.completeSale = async function() {
  if(state.cart.length === 0) return showToast('Savat bo\'sh', 'warning');
  try {
    const items = state.cart.map(c => ({ product_id: c.product_id, miqdor: c.miqdor }));
    const data = { items: items };
    if(sellSelectedCustomer) data.customer_id = sellSelectedCustomer.id;

    await Api.invoices.create(data);
    showToast('Faktura yaratildi va sotuv yakunlandi!', 'success');
    state.cart = [];
    sellSelectedCustomer = null;
    loadPage('sell');
  } catch(e) {
    showToast(e.message, 'error');
  }
}

async function renderInvoices(container) {
  const data = await Api.invoices.list(1, 50);
  let rows = '';
  data.items.forEach(inv => {
    const date = new Date(inv.yaratilgan_sana).toLocaleString();
    const statusClass = inv.status === 'yaratilgan' ? 'badge-green' : 'badge-red';
    rows += `<tr>
      <td><strong>${inv.faktura_raqami}</strong></td>
      <td>${date}</td>
      <td>${inv.umumiy_summa} so'm</td>
      <td><span class="badge ${statusClass}">${inv.status}</span></td>
      <td>
        ${inv.status === 'yaratilgan' ? `<button class="btn btn-sm btn-danger" onclick="cancelInvoice(${inv.id})">Bekor qilish</button>` : ''}
      </td>
    </tr>`;
  });
  container.innerHTML = `<div class="panel"><div class="table-wrap"><table><thead><tr><th>Faktura №</th><th>Sana</th><th>Summa</th><th>Status</th><th>Amal</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

window.cancelInvoice = async function(id) {
  if(!confirm("Haqiqatan ham bekor qilasizmi? Maxsulotlar omborga qaytadi!")) return;
  try {
    await Api.invoices.cancel(id);
    showToast('Faktura bekor qilindi', 'success');
    loadPage('invoices');
  } catch(e) {
    showToast(e.message, 'error');
  }
}
