"""Fix frontend initialization and create Evangelion-style UI."""
from pathlib import Path
import re

frontend_file = Path("/home/tone/crypto-dashboard/frontend/index.html")
html_content = frontend_file.read_text()

# Fix: remove the duplicate init block and add proper window.onload
old_init = r'''// ─── Init ───
\(async \(\) => \{
    await loadToken\(\);
    document\.getElementById\('last-update'\)\.textContent = 'Updated ' \+ new Date\(\)\.toLocaleTimeString\(\);
    setInterval\(\(\) => \{
        loadToken\(\); loadBridge\(\);
        if \(!document\.getElementById\('crosschain-tab'\)\.classList\.contains\('hidden'\)\) loadCrossChain\(\);
        if \(!document\.getElementById\('whale-tab'\)\.classList\.contains\('hidden'\)\) loadWhaleTab\(\);
    \}, 120000\); // auto-refresh 2min
\}\)\(\);

// Auto-refresh last refresh time every minute
setInterval\(loadLastRefresh, 60000\);'''

new_init = '''// ─── Init ───
window.onload = function() {
    loadToken();
    loadLastRefresh();
    setInterval(loadLastRefresh, 60000);  // Update refresh time every minute
};'''

html_content = re.sub(old_init, new_init, html_content, flags=re.DOTALL)

# Create Evangelion-style CSS
evangelion_css = '''<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Rajdhani:wght@400;600;700&family=Share+Tech+Mono&display=swap');
    
    body { 
        background: #0a0a0a; 
        color: #00ff41; 
        font-family: 'Rajdhani', sans-serif; 
        background-image: 
            linear-gradient(rgba(0, 255, 65, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 255, 65, 0.03) 1px, transparent 1px);
        background-size: 30px 30px;
    }
    
    .card { 
        background: linear-gradient(135deg, #111 0%, #0a0a0a 100%);
        border: 1px solid #00ff41;
        border-radius: 0;
        position: relative;
        overflow: hidden;
    }
    
    .card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, #00ff41, transparent);
        animation: scan 3s linear infinite;
    }
    
    .card::after {
        content: '';
        position: absolute;
        top: 0;
        right: 0;
        width: 20px;
        height: 20px;
        border: 2px solid #ff006e;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    
    @keyframes scan {
        0% { opacity: 0.3; }
        50% { opacity: 1; }
        100% { opacity: 0.3; }
    }
    
    @keyframes pulse {
        0%, 100% { transform: scale(0.8); opacity: 0.5; }
        50% { transform: scale(1.2); opacity: 1; }
    }
    
    .tab-active { 
        background: #00ff41 !important; 
        color: #000 !important; 
        border: 2px solid #00ff41 !important;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .tab-inactive { 
        background: transparent !important; 
        color: #00ff41 !important; 
        border: 1px solid #00ff4180 !important;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .tab-inactive:hover { 
        background: #00ff4120 !important;
        border-color: #00ff41 !important;
    }
    
    .glow { 
        box-shadow: 0 0 30px rgba(0, 255, 65, 0.3), inset 0 0 30px rgba(0, 255, 65, 0.05);
    }
    
    .magenta { color: #ff006e; }
    .orange { color: #ff6b00; }
    .cyan { color: #00ffff; }
    
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-thumb { background: #00ff41; border-radius: 0; }
    ::-webkit-scrollbar-track { background: #0a0a0a; }
    
    .num-mono { 
        font-family: 'Share Tech Mono', 'Fira Code', monospace; 
        text-shadow: 0 0 10px #00ff41;
        color: #00ff41 !important;
    }
    
    header {
        background: linear-gradient(90deg, #0a0a0a 0%, #111 50%, #0a0a0a 100%);
        border-bottom: 2px solid #00ff41;
        box-shadow: 0 4px 20px rgba(0, 255, 65, 0.2);
    }
    
    button.bg-brand-600 {
        background: #ff6b00;
        color: #000;
        border: 2px solid #ff6b00;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    
    button.bg-brand-600:hover {
        background: transparent;
        color: #ff6b00;
        box-shadow: 0 0 20px rgba(255, 107, 0, 0.5);
    }
    
    select, input {
        background: #000;
        border: 1px solid #00ff41;
        color: #00ff41;
        font-family: 'Share Tech Mono', monospace;
    }
    
    select:focus, input:focus {
        outline: none;
        border-color: #ff6b00;
        box-shadow: 0 0 10px rgba(255, 107, 0, 0.5);
    }
    
    h1, h2, h3 {
        text-transform: uppercase;
        letter-spacing: 3px;
        font-family: 'Orbitron', sans-serif;
    }
    
    p, span, td, th {
        font-family: 'Rajdhani', sans-serif;
    }
    
    table {
        border: 1px solid #00ff4140;
        background: #0a0a0a;
    }
    
    th {
        background: #00ff4120;
        text-transform: uppercase;
        letter-spacing: 2px;
        border-bottom: 1px solid #00ff41;
    }
    
    tr {
        border-bottom: 1px solid #00ff4120;
    }
    
    tr:hover {
        background: #00ff4110;
    }
    
    a {
        color: #00ffff;
        text-shadow: 0 0 5px #00ffff;
    }
    
    .text-slate-400 { color: #00ff4180 !important; }
    .text-slate-500 { color: #00ff4160 !important; }
    .text-slate-300 { color: #00ff41 !important; }
    
    .text-green-400 { color: #00ff41 !important; }
    .text-purple-400 { color: #ff006e !important; }
    .text-cyan-400 { color: #00ffff !important; }
    .text-blue-400 { color: #0066ff !important; }
    .text-red-400 { color: #ff0040 !important; }
    .text-yellow-400 { color: #ffcc00 !important; }
    
    .bg-brand-600 { background: #ff6b00 !important; }
    .hover\\:bg-brand-500:hover { background: #ff8800 !important; }
</style>'''

# Replace the old style section
old_style = r'<style>.*?</style>'
html_content = re.sub(old_style, evangelion_css, html_content, flags=re.DOTALL)

print("✅ Updated Evangelion-style UI")
print(f"Total lines: {len(html_content.splitlines())}")

frontend_file.write_text(html_content)
print(f"✅ Saved to {frontend_file}")