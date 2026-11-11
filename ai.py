from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
from openai import OpenAI
import streamlit as st

from analysis import AnalysisPlan, column_context, validate_plan


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets["OPENAI_API_KEY"]
        except (FileNotFoundError, KeyError):
            api_key = None
    if not api_key:
        raise RuntimeError(
            "Set OPENAI_API_KEY in your environment variables or Streamlit secrets."
        )
    return OpenAI(api_key=api_key)


def create_analysis_plan(
    question: str, dataframe: pd.DataFrame, model: str
) -> AnalysisPlan:
    client = _client()
    columns = column_context(dataframe)
    prompt = {
        "question": question,
        "columns": columns,
        "rules": [
            "Choose only columns listed; do not invent names.",
            "Use metric only for a numeric column.",
            "Use aggregation=count for questions about record counts.",
            "Use dimension=null for a single ungrouped metric.",
            "bar, line, and pie require a dimension.",
            "scatter requires a numeric metric and numeric dimension.",
            "histogram requires a numeric metric.",
            "Return only the requested JSON object.",
        ],
    }
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Turn business questions into analysis plans for a dashboard. "
                    "Do not calculate results. Reply with JSON containing title, "
                    "metric (string or null), dimension (string or null), aggregation "
                    "(sum, mean, median, min, max, or count), chart_type (bar, line, "
                    "pie, scatter, histogram, table, or metric), and limit (integer "
                    "from 1 to 20). Write titles and summaries in English."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The AI returned an empty response while creating the analysis.")
    raw_plan: dict[str, Any] = json.loads(content)
    return validate_plan(raw_plan, dataframe)


def create_executive_summary(
    question: str,
    plan: AnalysisPlan,
    result: pd.DataFrame,
    row_count: int,
    model: str,
) -> str:
    client = _client()
    context = {
        "question": question,
        "analysis": {
            "title": plan.title,
            "metric": plan.metric,
            "dimension": plan.dimension,
            "aggregation": plan.aggregation,
            "chart_type": plan.chart_type,
        },
        "dataset_row_count": row_count,
    }
    if plan.chart_type == "histogram":
        values = result[plan.metric]
        context["metric_summary"] = {
            "count": int(values.count()),
            "mean": values.mean(),
            "median": values.median(),
            "min": values.min(),
            "max": values.max(),
        }
    elif plan.chart_type == "scatter":
        context["plot_summary"] = {
            column: {
                "count": int(result[column].count()),
                "mean": result[column].mean(),
                "min": result[column].min(),
                "max": result[column].max(),
            }
            for column in (plan.dimension, plan.metric)
        }
    else:
        context["aggregated_result"] = result.to_dict(orient="records")[:20]
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "Write a concise executive summary in English using only the "
                    "provided results. Highlight the main finding and a relevant "
                    "caveat. Do not invent causes, trends, or values; if the results "
                    "do not support a conclusion, say so."
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False, default=str)},
        ],
    )
    summary = response.choices[0].message.content
    if not summary or not summary.strip():
        raise RuntimeError("The AI returned an empty executive summary.")
    return summary.strip()
