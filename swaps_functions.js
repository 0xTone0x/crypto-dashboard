async function loadSwapsFeed() {
    const minUsd = document.getElementById('swaps-usd-filter')?.value || 'all';
    const data = await api('/token/swaps?limit=100');
    if (data && data.swaps) renderSwapsFeed(data.swaps, minUsd);
}

function renderSwapsFeed(swaps, minUsd) {
    const container = document.getElementById('swaps-feed');
    if (!container) return;
    
    // Filter by USD value
    let filtered = swaps;
    if (minUsd === '100') {
        filtered = swaps.filter(s => s.usd_amount >= 100);
    } else if (minUsd === '1000') {
        filtered = swaps.filter(s => s.usd_amount >= 1000);
    }
    
    if (!filtered.length) {
        container.innerHTML = '<p class="text-center text-slate-500 py-4">No swaps match filter</p>';
        return;
    }
    
    container.innerHTML = filtered.map(s => {
        let typeEmoji, typeClass, typeText;
        if (s.type === 'BUY') { typeEmoji = '🟢'; typeClass = 'text-green-400'; typeText = 'BUY'; }
        else if (s.type === 'SELL') { typeEmoji = '🔴'; typeClass = 'text-red-400'; typeText = 'SELL'; }
        else { typeEmoji = '🔄'; typeClass = 'text-yellow-400'; typeText = 'SWAP'; }
        
        let activityInfo = '';
        if (s.activity_6h && s.activity_6h.is_accumulating) {
            activityInfo = '<div class="text-green-400 text-xs">📈 Accumulating (6h: +' + s.activity_6h.net + ' NOXA)</div>';
        } else if (s.activity_6h && s.activity_6h.is_distributing) {
            activityInfo = '<div class="text-red-400 text-xs">📉 Distributing (6h: ' + s.activity_6h.net + ' NOXA)</div>';
        } else if (s.activity_6h) {
            activityInfo = '<div class="text-slate-500 text-xs">⚖️ Balanced (6h: ' + s.activity_6h.net + ' NOXA)</div>';
        }
        
        return '<div class="border-b border-slate-700/50 pb-2 mb-2">' +
            '<div class="' + typeClass + ' font-bold text-sm">' + typeEmoji + ' ' + typeText + ' ' + s.amount_str + ' $NOXA</div>' +
            '<div class="text-xs text-slate-400 mt-1">' +
            '<div class="grid grid-cols-2 gap-1">' +
            '<div>💰 ' + s.price_usd_str + '</div>' +
            '<div>💵 ' + s.usd_amount_str + '</div>' +
            '<div>💼 ' + s.wallet_balance_str + '</div>' +
            '<div>' + activityInfo + '</div>' +
            '<div class="col-span-2">👤 ' + s.wallet_short + ' | 🕐 ' + s.time_utc + '</div>' +
            '</div></div></div>';
    }).join('');
}

async function loadLastRefresh() {
    const data = await api('/token/last-refresh');
    if (data) {
        const el = document.getElementById('last-refresh');
        if (el) {
            const fmtTime = (ts) => {
                if (!ts) return '—';
                const d = new Date(ts);
                return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
            };
            el.innerHTML = 'Last refresh: <strong>' + fmtTime(data.token_last_block) + '</strong>';
        }
    }
}