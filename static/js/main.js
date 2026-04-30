// ===== PRODUCT PICKER (for forms with product lists) =====
let produseLista = [];

function initProductPicker(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Adauga primul rand
    addProductRow(container);
}

function addProductRow(container) {
    const rowId = Date.now();
    const div = document.createElement('div');
    div.className = 'product-row d-flex align-items-center gap-2';
    div.dataset.rowId = rowId;
    div.innerHTML = `
        <div class="flex-grow-1 position-relative">
            <input type="text" class="form-control form-control-sm product-search"
                   placeholder="Cauta produs..." autocomplete="off"
                   data-row="${rowId}">
            <div class="autocomplete-list d-none" id="ac-${rowId}"></div>
            <input type="hidden" class="produs-id" data-row="${rowId}">
            <input type="hidden" class="produs-um" data-row="${rowId}" value="buc">
        </div>
        <div style="width:110px">
            <input type="number" class="form-control form-control-sm cantitate-input"
                   placeholder="Cant." min="0" step="0.001" data-row="${rowId}">
        </div>
        <div style="width:50px" class="text-center">
            <span class="badge-um um-label" data-row="${rowId}">buc</span>
        </div>
        <div style="width:110px" class="pret-container d-none">
            <input type="number" class="form-control form-control-sm pret-input"
                   placeholder="Pret" min="0" step="0.01" data-row="${rowId}">
        </div>
        <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeProductRow(this)">
            <i class="bi bi-trash"></i>
        </button>
    `;
    container.appendChild(div);

    // Bind search
    const searchInput = div.querySelector('.product-search');
    const acList = div.querySelector('.autocomplete-list');
    const produsIdInput = div.querySelector('.produs-id');
    const umInput = div.querySelector('.produs-um');
    const umLabel = div.querySelector('.um-label');

    searchInput.addEventListener('input', function() {
        const q = this.value.trim();
        if (q.length < 2) { acList.classList.add('d-none'); return; }
        fetch(`/produse/api/search?q=${encodeURIComponent(q)}`)
            .then(r => r.json())
            .then(data => {
                acList.innerHTML = '';
                if (data.length === 0) { acList.classList.add('d-none'); return; }
                data.forEach(p => {
                    const item = document.createElement('div');
                    item.className = 'autocomplete-item';
                    item.innerHTML = `<strong>${p.denumire}</strong> <small class="text-muted">${p.cod_articol || ''} · ${p.unitate_masura}</small>`;
                    item.addEventListener('click', () => {
                        searchInput.value = p.denumire;
                        produsIdInput.value = p.id;
                        umInput.value = p.unitate_masura;
                        umLabel.textContent = p.unitate_masura;
                        acList.classList.add('d-none');
                        // Arata pretul daca e disponibil
                        const pretContainer = div.querySelector('.pret-container');
                        if (pretContainer) {
                            pretContainer.classList.remove('d-none');
                            const pretInput = div.querySelector('.pret-input');
                            if (pretInput && p.pret_achizitie) pretInput.value = p.pret_achizitie;
                        }
                    });
                    acList.appendChild(item);
                });
                acList.classList.remove('d-none');
            });
    });

    document.addEventListener('click', function(e) {
        if (!div.contains(e.target)) acList.classList.add('d-none');
    });
}

function removeProductRow(btn) {
    const row = btn.closest('.product-row');
    const container = row.parentElement;
    if (container.querySelectorAll('.product-row').length > 1) {
        row.remove();
    }
}

function collectProducts(containerId, includePrice = false) {
    const container = document.getElementById(containerId);
    if (!container) return [];
    const rows = container.querySelectorAll('.product-row');
    const result = [];
    rows.forEach(row => {
        const produsId = row.querySelector('.produs-id').value;
        const cantitate = parseFloat(row.querySelector('.cantitate-input').value || 0);
        if (!produsId || cantitate <= 0) return;
        const obj = { produs_id: parseInt(produsId), cantitate: cantitate };
        if (includePrice) {
            const pretInput = row.querySelector('.pret-input');
            obj.pret_unitar = pretInput ? parseFloat(pretInput.value || 0) : 0;
        }
        result.push(obj);
    });
    return result;
}

// ===== FORMAT NUMBERS =====
function formatNumber(n, decimals = 2) {
    return new Intl.NumberFormat('ro-RO', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(n);
}

// ===== AUTO-DISMISS ALERTS =====
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(() => {
        document.querySelectorAll('.alert-success').forEach(a => {
            const bsAlert = new bootstrap.Alert(a);
            bsAlert.close();
        });
    }, 4000);
});
