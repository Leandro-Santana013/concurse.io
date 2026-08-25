import os, sys, glob, json

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

corpus_files = glob.glob('training_corpus/*.json')
print(f"Total files in training_corpus: {len(corpus_files)}")

# Check first 5 corpus files
for f in corpus_files[:5]:
    try:
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
            if isinstance(data, list):
                print(f"{os.path.basename(f)}: list of {len(data)} items")
                if data:
                    print(f"   Sample keys: {list(data[0].keys())}")
            elif isinstance(data, dict):
                print(f"{os.path.basename(f)}: dict keys: {list(data.keys())}")
    except Exception as e:
        print(f"{os.path.basename(f)}: ERROR {e}")
