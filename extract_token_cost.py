import json
import csv
import os

INPUT = os.path.join("output", "grading_results.json")
OUT_PROMPT = os.path.join("output", "prompt_tokens.csv")
OUT_COMPLETION = os.path.join("output", "completion_tokens.csv")
OUT_COST = os.path.join("output", "cost_summary.txt")

# Claude Sonnet 4.6 pricing (USD per 1M tokens)
PRICE_INPUT_PER_M = 0.104
PRICE_OUTPUT_PER_M = 0.416

with open(INPUT, encoding="utf-8") as f:
    data = json.load(f)

samples = data  # root is a list of sample results

prompt_list = []
completion_list = []
total_prompt = 0
total_completion = 0

for s in samples:
    usage = s.get("token_usage", {})
    p = usage.get("prompt_tokens", 0)
    c = usage.get("completion_tokens", 0)
    prompt_list.append(p)
    completion_list.append(c)
    total_prompt += p
    total_completion += c

with open(OUT_PROMPT, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["prompt_tokens"])
    for v in prompt_list:
        writer.writerow([v])

with open(OUT_COMPLETION, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["completion_tokens"])
    for v in completion_list:
        writer.writerow([v])

cost_input = total_prompt / 1_000_000 * PRICE_INPUT_PER_M
cost_output = total_completion / 1_000_000 * PRICE_OUTPUT_PER_M
cost_total = cost_input + cost_output

summary = f"""=== Token Usage & Cost Summary ===
Model: Claude Sonnet 4.6
Samples: {len(samples)}

Prompt tokens:     {total_prompt:>12,}   @ ${PRICE_INPUT_PER_M}/MTok  = ${cost_input:.4f}
Completion tokens: {total_completion:>12,}   @ ${PRICE_OUTPUT_PER_M}/MTok = ${cost_output:.4f}
Total tokens:      {total_prompt + total_completion:>12,}

Estimated cost: ${cost_total:.4f} USD
"""

print(summary)

with open(OUT_COST, "w", encoding="utf-8") as f:
    f.write(summary)

print(f"Saved: {OUT_PROMPT}")
print(f"Saved: {OUT_COMPLETION}")
print(f"Saved: {OUT_COST}")
