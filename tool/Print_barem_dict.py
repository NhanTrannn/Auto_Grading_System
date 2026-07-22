import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipeline

barem_dict = pipeline.load_barem(barem_path="sample_parem.json")
with open("barem_dict.json", "w", encoding="utf-8") as f:
    json.dump(barem_dict, f, indent=4, ensure_ascii=False)
    
