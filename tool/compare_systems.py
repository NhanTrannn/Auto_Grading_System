import json

systems = {}
for i in range(1, 5):
    try:
        with open(f"grading_results_s{i}.json") as f:
            data = json.load(f)
            systems[i] = (data["total_score"], data["total_max_score"])
    except:
        pass

print("\n" + "=" * 60)
print("GRADING SYSTEM COMPARISON (CoT Implementation)")
print("=" * 60)

results = [
    ("S1 (Heuristic only)", systems.get(1)),
    ("S2 (Hybrid + CoT)", systems.get(2)),
    ("S3 (Pure LLM + CoT)", systems.get(3)),
    ("S4 (LLM+Advisory + CoT)", systems.get(4)),
]

for name, score in results:
    if score:
        s, max_s = score
        pct = s / max_s * 100
        print(f"{name:30} {s:5.2f}/{max_s:4.2f} = {pct:5.1f}%")
    else:
        print(f"{name:30} N/A")

print("=" * 60)
