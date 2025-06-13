import os
import pandas as pd
import folium
import numpy as np
import subprocess
import gspread
import hashlib
import json
from oauth2client.service_account import ServiceAccountCredentials

# === Step 1: Load Google Sheet ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Heatmap Master Sheet HALOS").sheet1
data = sheet.get_all_records()

# === Smart update: skip if sheet hasn't changed ===
def sheet_hash(data):
    json_data = json.dumps(data, sort_keys=True)
    return hashlib.sha256(json_data.encode('utf-8')).hexdigest()

new_hash = sheet_hash(data)
HASH_FILE = "last_sheet_hash.txt"
previous_hash = ""

if os.path.exists(HASH_FILE):
    with open(HASH_FILE, "r") as f:
        previous_hash = f.read().strip()

if new_hash == previous_hash:
    print("✅ Sheet has not changed. Skipping update.")
    exit()

with open(HASH_FILE, "w") as f:
    f.write(new_hash)

# === Convert sheet data ===
addresses_df = pd.DataFrame(data)
addresses_df = addresses_df.drop(columns=["#", "Notes"], errors="ignore")

# Convert numeric columns safely
addresses_df['ARR Total'] = pd.to_numeric(addresses_df['ARR Total'], errors='coerce')
addresses_df['Latitude'] = pd.to_numeric(addresses_df['Latitude'], errors='coerce')
addresses_df['Longitude'] = pd.to_numeric(addresses_df['Longitude'], errors='coerce')

# ❗ Drop rows missing location or ARR
addresses_df = addresses_df.dropna(subset=['Latitude', 'Longitude', 'ARR Total'])

# Sort after cleaning
addresses_df = addresses_df.sort_values(by='ARR Total')


map_center = [37.0902, -95.7129]
mymap = folium.Map(location=map_center, zoom_start=5, min_zoom=5, max_zoom=10)

def get_marker_color(arr):
    if arr <= 10000: return 'green'
    elif arr <= 25000: return 'yellow'
    elif arr <= 50000: return 'orange'
    elif arr <= 100000: return 'red'
    else: return 'purple'

arr_color_data = {c: {'count': 0, 'total': 0} for c in ['green', 'yellow', 'orange', 'red', 'purple']}
region_data = {r: {'count': 0, 'total': 0} for r in ['West', 'Central', 'East']}

for _, row in addresses_df.iterrows():
    arr_total = row['ARR Total']
    lat, lon = row['Latitude'], row['Longitude']
    color = get_marker_color(arr_total)
    arr_color_data[color]['count'] += 1
    arr_color_data[color]['total'] += arr_total
    region = 'West' if lon < -109 else 'Central' if lon <= -90 else 'East'
    region_data[region]['count'] += 1
    region_data[region]['total'] += arr_total

    radius = 3 + (np.log1p(arr_total) * 0.6)
    folium.CircleMarker(
        location=[lat, lon],
        radius=radius,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.6,
        popup=f"<b>{row['Name']}</b><br>{row['Address']}<br>ARR: ${arr_total:,.2f}"
    ).add_to(mymap)

# === Add ARR Legend ===
legend_html = f"""
<div style="position: fixed; bottom: 10px; left: 10px; width: 300px; height: 240px;
             background-color: white; border:2px solid grey; z-index:9999; font-size:13px;
             padding: 15px 10px 10px 10px; border-radius: 5px;">
<b style="text-align: center; display: block; margin-bottom: 8px;">ARR Breakdown by Tier</b>
""" + "".join([
    f"<i style='background:{color}; width: 20px; height: 20px; display: inline-block;'></i> "
    f"{tier} — {arr_color_data[color]['count']} clients, ${arr_color_data[color]['total']:,.0f}<br>"
    for color, tier in zip(
        ['green', 'yellow', 'orange', 'red', 'purple'],
        ['< $10K', '$10K–25K', '$25K–50K', '$50K–100K', '> $100K']
    )
]) + "</div>"

mymap.get_root().html.add_child(folium.Element(legend_html))

# === Add Region Breakdown ===
region_html = f"""
<div style="position: fixed; top: 10px; left: 10px; width: 280px; height: 140px;
             background-color: white; border:2px solid grey; z-index:9999; font-size:13px;
             padding: 15px 10px 10px 10px; border-radius: 5px;">
<b style="text-align: center; display: block; margin-bottom: 8px;">ARR by U.S. Region</b>
""" + "".join([
    f"<b>{region}</b>: {region_data[region]['count']} clients, ${region_data[region]['total']:,.0f}<br>"
    for region in ['West', 'Central', 'East']
]) + "</div>"

mymap.get_root().html.add_child(folium.Element(region_html))

# Add vertical region dividers
for line in [-109, -90]:
    folium.PolyLine([[25, line], [50, line]], color='black', weight=2, opacity=0.3, dash_array='5,5').add_to(mymap)

# === Step 4: Save the map ===
mymap.save("index_raw.html")

# === Step 5: Inject SHA-256 Password Protection ===
PASSWORD_HASH = "5c86dc9f9cdb39dd68c5f7f112406f8ce987972afab08d5605d862bbb3609cd4"  # halos2025

with open("index_raw.html", "r", encoding="utf-8") as f:
    content = f.read()

security_script = """
<script>
window.onload = async function () {
  const bot = /HubSpot|HubSpot-Webhooks|HubSpot-Crawler|bot|crawl|spider/i.test(navigator.userAgent);
  if (bot) return; // allow bots

  const validHash = "5c86dc9f9cdb39dd68c5f7f112406f8ce987972afab08d5605d862bbb3609cd4"; // SHA-256 of 'halos2025'

  // 1. Check if the access code is in the URL:
  let access = new URLSearchParams(window.location.search).get("access");

  // 2. If not, prompt the user:
  if (!access) {
    access = prompt("Enter access code:");
  }

  // 3. If user cancels prompt, block access:
  if (!access) {
    document.body.innerHTML = "<h2 style='color:red; text-align:center;'>Access Denied</h2>";
    return;
  }

  // 4. Hash and check the access code:
  const encoder = new TextEncoder();
  const data = encoder.encode(access);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  if (hashHex === validHash) return; // ✅ valid

  // 5. Block access if invalid:
  document.body.innerHTML = "<h2 style='color:red; text-align:center;'>Access Denied</h2>";
};
</script>

"""

content = content.replace("<head>", f"<head>{security_script}", 1)

# Add "Update Map" button
trigger_html = """
<button onclick="triggerUpdate()" style="
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 9999;
    padding: 12px 20px;
    background-color: #0070f3;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
">
  🔄 Update Map
</button>
<script>
  async function triggerUpdate() {
    const res = await fetch('/api/trigger', { method: 'POST' });
    const json = await res.json();
    alert(json.message || json.error);
  }
</script>
"""

content = content.replace("</body>", trigger_html + "\n</body>")

with open("index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ index.html created with SHA-256 password gate.")

# === Step 6: Auto Git Push ===
try:
    subprocess.run(["git", "add", "index.html"], check=True)
    subprocess.run(["git", "commit", "-m", "Auto update from Google Sheet"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("🚀 Pushed to GitHub!")
except subprocess.CalledProcessError:
    print("ℹ️ Nothing to commit (no changes).")
