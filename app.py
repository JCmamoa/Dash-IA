from __future__ import annotations

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from openai import OpenAIError

from ai import create_analysis_plan, create_executive_summary
from analysis import AnalysisPlan, execute_plan


ROOT = Path(__file__).parent
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

st.set_page_config(
    page_title="Nexo | AI-Powered Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: #f5f7fb; }
    [data-testid="stSidebar"] { background: #101c35; }
    [data-testid="stSidebar"] * { color: #eef3ff; }
    .hero {
        padding: 1.4rem 1.7rem;
        border-radius: 18px;
        background: linear-gradient(115deg, #102447, #2256a2);
        color: white;
        margin-bottom: 1.1rem;
    }
    .hero h1 { margin: 0 0 .35rem 0; font-size: 2rem; }
    .hero p { margin: 0; color: #d7e5ff; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def read_csv(contents: bytes, filename: str, separator: str) -> pd.DataFrame:
    return pd.read_csv(
        pd.io.common.BytesIO(contents),
        sep=separator,
        encoding="utf-8-sig",
    )


def render_chart(result: pd.DataFrame, plan: AnalysisPlan) -> None:
    if plan.chart_type == "table":
        st.dataframe(result, use_container_width=True, hide_index=True)
    elif plan.chart_type == "metric":
        st.metric(plan.title, _format_value(result.iloc[0, 0]))
    elif plan.chart_type == "histogram":
        chart = (
            alt.Chart(result)
            .mark_bar(color="#2878d0")
            .encode(
                x=alt.X(f"{plan.metric}:Q", bin=alt.Bin(maxbins=25), title=plan.metric),
                y=alt.Y("count():Q", title="Records"),
                tooltip=[alt.Tooltip("count():Q", title="Records")],
            )
            .properties(height=360)
        )
        st.altair_chart(chart, use_container_width=True)
    elif plan.chart_type == "scatter":
        chart = (
            alt.Chart(result)
            .mark_circle(size=65, opacity=0.65, color="#2878d0")
            .encode(
                x=alt.X(f"{plan.dimension}:Q", title=plan.dimension),
                y=alt.Y(f"{plan.metric}:Q", title=plan.metric),
                tooltip=[plan.dimension, plan.metric],
            )
            .properties(height=360)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        value_column = "Result"
        dimension = plan.dimension
        chart = alt.Chart(result)
        if plan.chart_type == "pie":
            chart = chart.mark_arc(outerRadius=130).encode(
                theta=alt.Theta(f"{value_column}:Q"),
                color=alt.Color(f"{dimension}:N", title=dimension),
                tooltip=[dimension, value_column],
            )
        else:
            mark = "line" if plan.chart_type == "line" else "bar"
            chart = getattr(chart, f"mark_{mark}")(color="#2878d0")
            chart = chart.encode(
                x=alt.X(f"{dimension}:N", sort="-y", title=dimension),
                y=alt.Y(f"{value_column}:Q", title=value_column),
                tooltip=[dimension, value_column],
            )
        st.altair_chart(chart.properties(height=360), use_container_width=True)


def _format_value(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


st.markdown(
    """
    <div class="hero">
      <h1>Nexo <span style="font-weight:400">| Intelligence for better decisions</span></h1>
      <p>Ask a question. Explore your data. Find your next move.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## 📊 Nexo Analytics")
    st.caption("AI-powered analytics dashboard")
    st.markdown("---")
    st.markdown("**Get started**")
    st.markdown("1. Upload a CSV or load the sample data.\n2. Ask a question about your data.\n3. Review the chart and executive summary.")
    st.markdown("---")
    st.caption(f"Model: `{MODEL}`")
    st.caption("Your complete dataset is analyzed locally.")

upload_col, separator_col = st.columns([4, 1])
with upload_col:
    uploaded_file = st.file_uploader("Upload your dataset", type=["csv"])
with separator_col:
    separator_label = st.selectbox("Delimiter", ["Comma (,)", "Semicolon (;)"], index=0)

use_sample = st.checkbox("Use the sample sales dataset")
dataframe: pd.DataFrame | None = None
data_source = ""

try:
    if use_sample:
        dataframe = pd.read_csv(ROOT / "sample_data" / "sales.csv")
        data_source = "Sample dataset"
    elif uploaded_file is not None:
        separator = "," if separator_label.startswith("Comma") else ";"
        dataframe = read_csv(uploaded_file.getvalue(), uploaded_file.name, separator)
        data_source = uploaded_file.name
except (UnicodeDecodeError, pd.errors.ParserError, OSError) as exc:
    st.error(f"Could not read the CSV: {exc}")

if dataframe is not None:
    if dataframe.empty:
        st.error("The file contains no records.")
    elif dataframe.shape[1] < 1:
        st.error("The file contains no columns.")
    else:
        st.caption(
            f"**{data_source}** · {len(dataframe):,} records · "
            f"{len(dataframe.columns)} columns"
        )
        with st.expander("Data preview", expanded=False):
            st.dataframe(dataframe.head(8), use_container_width=True, hide_index=True)

        with st.form("analysis_form"):
            question = st.text_input(
                "What would you like to find out?",
                placeholder="e.g., Which regions sold the most units?",
                max_chars=500,
            )
            send_to_ai = st.checkbox(
                "I authorize sending my question, column names/types, and aggregated "
                "results to the OpenAI API to generate the analysis and summary. "
                "Full CSV rows are not sent."
            )
            submitted = st.form_submit_button(
                "✨ Analyze with AI", type="primary", use_container_width=True
            )

        if submitted:
            if not question.strip():
                st.warning("Enter a question to start the analysis.")
            elif not send_to_ai:
                st.warning("Authorize the use of the AI API to continue.")
            else:
                try:
                    with st.spinner("Interpreting your question and analyzing the data..."):
                        plan = create_analysis_plan(question, dataframe, MODEL)
                        result = execute_plan(dataframe, plan)
                        summary = create_executive_summary(
                            question, plan, result, len(dataframe), MODEL
                        )
                    st.session_state["analysis_result"] = {
                        "plan": plan,
                        "result": result,
                        "summary": summary,
                        "question": question.strip(),
                    }
                except (OpenAIError, RuntimeError, ValueError) as exc:
                    st.error(f"Could not complete the analysis: {exc}")
                except (KeyError, IndexError) as exc:
                    st.error(
                        "The AI returned an unexpected response. "
                        f"Try rephrasing your question. ({type(exc).__name__})"
                    )

        analysis = st.session_state.get("analysis_result")
        if analysis:
            plan = analysis["plan"]
            result = analysis["result"]
            st.markdown("---")
            st.subheader(plan.title)
            st.markdown("### Executive summary")
            st.info(analysis["summary"])
            st.markdown("### Visualization")
            render_chart(result, plan)
            if plan.chart_type != "metric":
                st.download_button(
                    "⬇️ Download results (CSV)",
                    data=result.to_csv(index=False).encode("utf-8-sig"),
                    file_name="analysis_results.csv",
                    mime="text/csv",
                )
else:
    st.info("Upload a CSV file or select the sample dataset to get started.")
