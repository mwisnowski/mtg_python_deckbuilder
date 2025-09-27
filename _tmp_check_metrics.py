import urllib.request, json
raw = urllib.request.urlopen("http://localhost:8000/themes/metrics").read().decode()
js=json.loads(raw)
print('example_enforcement_active=', js.get('preview',{}).get('example_enforcement_active'))
print('example_enforce_threshold_pct=', js.get('preview',{}).get('example_enforce_threshold_pct'))
