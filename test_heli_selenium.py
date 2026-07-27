import time, json, sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-gpu')

driver = webdriver.Chrome(options=opts)
driver.get('file:///C:/Users/e/Desktop/4a/test_physics.html')
time.sleep(2)

results = driver.find_element(By.ID, 'results')
text = results.text

print(text)

divs = results.find_elements(By.TAG_NAME, 'div')
fails = []
passes = []
for d in divs:
    cls = d.get_attribute('class')
    t = d.text
    if cls == 'fail':
        fails.append(t)
    elif cls == 'pass':
        passes.append(t)

print(f"\n{'='*60}")
print(f"TOTAL: {len(passes)} passed, {len(fails)} failed")
print(f"{'='*60}")

if fails:
    print("\nFAILURES:")
    for f in fails:
        print(f"  {f}")

driver.quit()
sys.exit(1 if fails else 0)
