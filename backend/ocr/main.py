"""
OCR -> grading bridge: runs ocr_main.py's OCR connector (module1/2/3), then
grades the freshly-produced Results-format JSON through ../pipeline.py in
the same command.

Two-step, one command:
  1. build_results_json() (ocr_main.py, in-process import) — align each
     student page to the template (module2), crop every ROI, OCR it
     (module3), write the "Results" JSON pipeline.py's load_input() expects.
  2. Shell out to ../pipeline.py via `subprocess` (SAME interpreter running
     this script) to grade that JSON against a barem — equivalent to running
     `python pipeline.py --input ... --barem ... --output-dir ...` by hand.

Step 2 is a subprocess rather than an in-process `import pipeline` purely so
this script stays equivalent to typing the two commands by hand — pipeline.py
keeps its own working directory (backend/) and its own stdout formatting. It
is not a dependency boundary: backend/ has one requirements.txt covering both
halves, and the web path (backend/app/pipeline_worker.py) imports both
directly in one process instead.

Usage (run from inside backend/ocr/, same as ocr_main.py):

    python main.py --config roi_config.json --output results.json \\
        --barem ../sample_parem.json --grade-output-dir ../testing/output

--config/--output/--save-crops behave exactly like ocr_main.py's own CLI —
see its module docstring for roi_config.json's shape. --barem/
--grade-output-dir/--progress-file are new here.

--progress-file writes a live JSON snapshot ({stage, done, total, message})
after every OCR'd ROI and again when grading starts/finishes, so a caller
that can't read stdout can still show a progress bar. The file is rewritten
atomically by ocr_main.write_progress, so a partial read is impossible. The
web API used to be that caller; it now imports build_results_json directly
and writes progress straight to its database, so this flag is only for
external scripts driving the CLI.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import ocr_main


def grade_with_pipeline(
    results_path: str,
    barem_path: str,
    output_dir: str,
    progress_file: str | None = None,
) -> None:
    """Equivalent to `python pipeline.py --input ... --barem ... --output-dir ...`."""
    pipeline_path = Path(__file__).resolve().parent.parent / "pipeline.py"
    if not pipeline_path.exists():
        raise FileNotFoundError(f"Không tìm thấy pipeline.py: {pipeline_path}")

    cmd = [
        sys.executable,
        str(pipeline_path),
        "--input", str(Path(results_path).resolve()),
        "--barem", str(Path(barem_path).resolve()),
        "--output-dir", str(Path(output_dir).resolve()),
    ]
    print(f"[main] Đang chấm điểm: {' '.join(cmd)}")
    ocr_main.write_progress(progress_file, "grading", 0, 1, "Đang chấm điểm bằng pipeline.py")
    # cwd=backend/ vì pipeline.py's .env lookup (load_dotenv()) và mọi path
    # tương đối khác của nó đều giả định chạy từ trong backend/, theo CLAUDE.md.
    subprocess.run(cmd, cwd=str(pipeline_path.parent), check=True)
    ocr_main.write_progress(progress_file, "grading", 1, 1, "Chấm điểm xong")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="roi_config.json path (see ocr_main.py)")
    parser.add_argument("--output", required=True, help="Output Results-format JSON path")
    parser.add_argument("--save-crops", action="store_true", help="Also save non-diagram crops to crop_dir (debugging)")
    parser.add_argument("--barem", required=True, help="Barem JSON path to grade --output against")
    parser.add_argument("--grade-output-dir", default="graded_output", help="Where pipeline.py writes grading_results.json/student_summary.json")
    parser.add_argument("--progress-file", help="Write live progress as JSON to this path (for a UI/progress bar)")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    result = ocr_main.build_results_json(
        config,
        save_crops=args.save_crops,
        on_progress=ocr_main.progress_writer(args.progress_file, "ocr"),
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[main] Wrote {args.output} ({sum(1 for k in result if k.startswith('HS_'))} students)")

    grade_with_pipeline(args.output, args.barem, args.grade_output_dir, args.progress_file)


if __name__ == "__main__":
    main()
