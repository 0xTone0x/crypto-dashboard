"""Update frontend JavaScript for time filters and price chart - fixed version."""
from pathlib import Path
import re

frontend_file = Path("/home/tone/crypto-dashboard/frontend/index.html")
html_content = frontend_file.read_text()

# 1. Update loadBridge() to use time filter
old_bridge_pattern = r"async function loadBridge\(\) \{[^}]*const \[stats, ts, dep, recent\] = await Promise\.all\(\[\s*api\('/api/bridge/stats'\),\s*api\('/api/bridge/timeseries'\),\s*api\('/api/bridge/top-depositors\?limit=20'\),\s*api\('/api/bridge/recent\?limit=20'\),\s*\]\);"

new_bridge_code = """async function loadBridge() {
    const hours = document.getElementById('bridge-time-filter').value;
    const windowLabel = hours === '0' ? 'All Time' : hours + 'h';
    document.getElementById('bridge-window-label').textContent = 'Window: ' + windowLabel;
    
    const [stats, ts, dep, recent] = await Promise.all([
        api('/api/bridge/stats?hours=' + hours),
        api('/api/bridge/timeseries'),
        api('/api/bridge/top-depositors?limit=20&hours=' + hours),
        api('/api/bridge/recent?limit=20'),
    ]);"""

# Find and replace the loadBridge function
match = re.search(old_bridge_pattern, html_content, re.DOTALL)
if match:
    html_content = html_content[:match.start()] + new_bridge_code + html_content[match.end():]
    print("✓ Updated loadBridge() with time filter")
else:
    print("! loadBridge() pattern not found - searching for loadBridge...")
    # Try to find it with a simpler pattern
    if "async function loadBridge()" in html_content:
        print("  Found loadBridge() but couldn't match the exact pattern")

# 2. Update loadCrossChain() to use time filter  
old_cc_pattern = r"async function loadCrossChain\(\) \{[^}]*const \[summary, matches\] = await Promise\.all\(\[\s*api\('/api/cross-chain/summary'\),\s*api\('/api/cross-chain/bridgers-buyers'\),\s*\]\);"

new_cc_code = """async function loadCrossChain() {
    const days = document.getElementById('crosschain-time-filter').value;
    const windowLabel = days === '0' ? 'All Time' : (days >= 1 ? days + 'd' : (days * 24) + 'h');
    document.getElementById('cc-window-label').textContent = 'Window: ' + windowLabel;
    
    const [summary, matches] = await Promise.all([
        api('/api/cross-chain/summary?days=' + days),
        api('/api/cross-chain/bridgers-buyers?days=' + days),
    ]);"""

match = re.search(old_cc_pattern, html_content, re.DOTALL)
if match:
    html_content = html_content[:match.start()] + new_cc_code + html_content[match.end():]
    print("✓ Updated loadCrossChain() with time filter")
else:
    print("! loadCrossChain() pattern not found")

# 3. Update loadWhale() to use heatmap time filter
old_whale_pattern = r"async function loadWhale\(\) \{[^}]*const \[alerts, heatmap, concentration\] = await Promise\.all\(\[\s*api\('/api/whale/alerts\?hours=24'\),\s*api\('/api/token/transfer-heatmap\?hours=24'\),\s*api\('/api/token/concentration-history'\),\s*\]\);"

new_whale_code = """async function loadWhale() {
    const hours = document.getElementById('heatmap-time-filter').value;
    
    const [alerts, heatmap, concentration] = await Promise.all([
        api('/api/whale/alerts?hours=' + hours),
        api('/api/token/transfer-heatmap?hours=' + hours),
        api('/api/token/concentration-history'),
    ]);"""

match = re.search(old_whale_pattern, html_content, re.DOTALL)
if match:
    html_content = html_content[:match.start()] + new_whale_code + html_content[match.end():]
    print("✓ Updated loadWhale() with time filter")
else:
    print("! loadWhale() pattern not found")

# 4. Add price chart and last refresh functions
price_chart_and_refresh = '''
async function loadPriceChart() {
    const data = await api('/api/token/price-history?limit=100');
    if (!data || !data.history) return;
    
    const ctx = document.getElementById('price-chart');
    if (!ctx) return;
    
    const labels = data.history.map(d => {
        const ts = new Date(d.timestamp);
        return ts.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    });
    const prices = data.history.map(d => d.price);
    
    if (window.priceChart) window.priceChart.destroy();
    window.priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'NOXA Price (USD)',
                data: prices,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 1,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: { 
                    display: true,
                    ticks: { color: '#64748b', maxTicksLimit: 8 },
                    grid: { color: '#1e293b' }
                },
                y: { 
                    display: true,
                    ticks: { color: '#64748b', callback: v => '$' + v.toFixed(2) },
                    grid: { color: '#1e293b' }
                }
            }
        }
    });
}

async function loadLastRefresh() {
    const data = await api('/api/token/last-refresh');
    if (!data) return;
    
    const priceTime = data.price_last_update || '—';
    
    let displayTime = '—';
    if (priceTime !== '—') {
        const ts = new Date(priceTime);
        const now = new Date();
        const diffMins = Math.floor((now - ts) / 60000);
        if (diffMins < 1) displayTime = 'Just now';
        else if (diffMins < 60) displayTime = diffMins + 'm ago';
        else displayTime = ts.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }
    
    document.getElementById('last-refresh').textContent = displayTime;
}
'''

# Insert these functions before the API helper section
if "// ─── API helper" in html_content:
    html_content = html_content.replace(
        "// ─── API helper",
        price_chart_and_refresh + "\n\n// ─── API helper"
    )
    print("✓ Added loadPriceChart() and loadLastRefresh() functions")
else:
    print("! API helper section not found")

# 5. Update loadToken() to call the new functions
if "async function loadToken()" in html_content:
    # Add the function calls at the start of loadToken
    old_token_start = "async function loadToken() {"
    new_token_start = "async function loadToken() {\n    await loadLastRefresh();\n    await loadPriceChart();"
    html_content = html_content.replace(old_token_start, new_token_start)
    print("✓ Updated loadToken() to load price chart and refresh time")
else:
    print("! loadToken() not found")

# 6. Add auto-refresh interval at the end
auto_refresh_code = '''
// Auto-refresh last refresh time every minute
setInterval(loadLastRefresh, 60000);
'''

# Find the closing script tag and add before it
script_end_pattern = r'(</script>)'
html_content = re.sub(script_end_pattern, auto_refresh_code + '\n' + r'\1', html_content)
print("✓ Added auto-refresh interval")

# Save the updated file
frontend_file.write_text(html_content)
print(f"\n✅ Saved all JavaScript updates to {frontend_file}")
print(f"Total lines: {len(html_content.splitlines())}")