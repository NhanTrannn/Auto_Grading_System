"""Demo Streamlit: upload input + barem, chấm bằng pipeline.py, xem kết quả."""

import json
import tempfile
from pathlib import Path

import streamlit as st

import pipeline as p

st.set_page_config(page_title="MMLAB Auto Grading - Demo", layout="wide")
st.title("MMLAB Auto Grading — Demo")
st.caption(
    "Upload file input (OCR Results format) và file barem, bấm Chấm bài để chạy pipeline thật. "
    "Lưu ý: mỗi lần chấm sẽ gọi LLM thật (tốn phí, có thể mất vài phút đến vài chục phút tuỳ số lượng câu/học sinh)."
)

col1, col2 = st.columns(2)
with col1:
    input_file = st.file_uploader("File input (JSON)", type=["json"], key="input_file")
with col2:
    barem_file = st.file_uploader("File barem (JSON)", type=["json"], key="barem_file")

run_clicked = st.button("Chấm bài", type="primary", disabled=not (input_file and barem_file))

if run_clicked:
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.json"
        barem_path = Path(tmpdir) / "barem.json"
        input_path.write_bytes(input_file.getvalue())
        barem_path.write_bytes(barem_file.getvalue())

        try:
            with st.spinner("Đang chấm bài (gọi LLM thật)..."):
                results = p.run_batch(str(input_path), str(barem_path))
        except Exception as e:
            st.error(f"Chấm bài thất bại: {e}")
            st.stop()

        st.session_state["results"] = results

results = st.session_state.get("results")

if results:
    total_score = sum(r.get("score", 0) or 0 for r in results)
    total_max = sum(r.get("max_score", 0) or 0 for r in results)
    pct = total_score / total_max * 100 if total_max else 0

    st.subheader("Tổng quan")
    m1, m2, m3 = st.columns(3)
    m1.metric("Tổng điểm", f"{total_score:.2f} / {total_max:.2f}")
    m2.metric("Tỷ lệ", f"{pct:.1f}%")
    m3.metric("Số câu đã chấm", len(results))

    summary = p.summarize_by_student(results)
    st.subheader("Theo học sinh")
    st.dataframe(
        [
            {
                "Học sinh": s["hs"],
                "Điểm": round(s["score"], 3),
                "Tối đa": round(s["max_score"], 3),
                "Câu sai": ", ".join(s.get("wrong", [])) or "-",
            }
            for s in summary
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Chi tiết từng câu")
    for r in results:
        sample_id = r.get("sample_id", "?")
        sc, mx = r.get("score", 0) or 0, r.get("max_score", 0) or 0
        status = r.get("status", "?")
        with st.expander(f"{sample_id} — {sc:.2f}/{mx:.2f} ({status})"):
            for cr in r.get("criterion_results") or []:
                cid = cr.get("criterion_id", "?")
                csc, cmx = cr.get("score", 0) or 0, cr.get("max_score", 0) or 0
                cstatus = cr.get("status", "?")
                st.markdown(f"**{cid}** — {csc:.2f}/{cmx:.2f} ({cstatus})")
                evidence = cr.get("evidence") or {}
                student_answer = evidence.get("student_answer")
                if student_answer:
                    st.code(student_answer, language="cpp")
                reasoning = cr.get("llm_reasoning") or cr.get("reason") or cr.get("feedback")
                if reasoning:
                    st.write(reasoning)
                st.divider()
else:
    st.info("Upload file input và barem rồi bấm Chấm bài để xem kết quả.")
