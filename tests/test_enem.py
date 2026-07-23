import sys
import os

# Ensure we can import app
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import app

def test_enem():
    print("Searching for ENEM...")
    # This uses DuckDuckGo and Gemini from app.py
    results = app._search_pdfs_web("ENEM prova pdf", os.environ.get("GEMINI_API_KEY", ""))
    print(f"Found {len(results)} results.")
    
    for r in results[:3]:
        print(f"\n--- Trying to download: {r['title']}")
        print(f"URL: {r['url']}")
        
        # Simulate download logic
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/pdf,*/*',
        }
        try:
            import warnings
            from urllib3.exceptions import InsecureRequestWarning
            warnings.filterwarnings('ignore', category=InsecureRequestWarning)
            resp = requests.get(r['url'], headers=headers, timeout=10, allow_redirects=True, verify=False)
            print(f"Requests Status: {resp.status_code}, Content-Type: {resp.headers.get('Content-Type')}")
            if resp.content[:4] == b'%PDF':
                print("SUCCESS: Downloaded via requests!")
            else:
                print("Failed: Not a PDF (starts with " + str(resp.content[:10]) + ")")
        except Exception as e:
            print(f"Requests error: {e}")

if __name__ == "__main__":
    test_enem()
