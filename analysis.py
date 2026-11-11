from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


AGGREGATIONS = {"sum", "mean", "median", "min", "max", "count"}
CHART_TYPES = {"bar", "line", "pie", "scatter", "histogram", "table", "metric"}


@dataclass(frozen=True)
class AnalysisPlan:
    title: str
    metric: str | None
    dimension: str | None
    aggregation: str
    chart_type: str
    limit: int


def validate_plan(raw_plan: dict[str, Any], dataframe: pd.DataFrame) -> AnalysisPlan:
    """Validate an AI-generated plan against the uploaded dataset."""
    title = raw_plan.get("title")
    metric = raw_plan.get("metric")
    dimension = raw_plan.get("dimension")
    aggregation = raw_plan.get("aggregation")
    chart_type = raw_plan.get("chart_type")
    limit = raw_plan.get("limit")

    if not isinstance(title, str) or not title.strip():
        raise ValueError("The AI did not return a valid analysis title.")
    if metric is not None and (not isinstance(metric, str) or metric not in dataframe.columns):
        raise ValueError("The AI selected a metric that does not exist in the file.")
    if dimension is not None and (
        not isinstance(dimension, str) or dimension not in dataframe.columns
    ):
        raise ValueError("The AI selected a dimension that does not exist in the file.")
    if aggregation not in AGGREGATIONS:
        raise ValueError("The AI selected an unsupported aggregation.")
    if chart_type not in CHART_TYPES:
        raise ValueError("The AI selected an unsupported chart type.")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise ValueError("The analysis result limit is invalid.")

    if aggregation != "count":
        if metric is None:
            raise ValueError("This aggregation requires a numeric column.")
        if not pd.api.types.is_numeric_dtype(dataframe[metric]):
            raise ValueError(f"Column '{metric}' is not numeric.")
    if chart_type in {"bar", "line", "pie"} and dimension is None:
        raise ValueError(f"The '{chart_type}' chart requires a dimension.")
    if chart_type == "scatter" and (
        metric is None
        or dimension is None
        or not pd.api.types.is_numeric_dtype(dataframe[dimension])
    ):
        raise ValueError("A scatter plot requires two numeric columns.")
    if chart_type == "histogram" and (
        metric is None or not pd.api.types.is_numeric_dtype(dataframe[metric])
    ):
        raise ValueError("A histogram requires a numeric metric.")

    return AnalysisPlan(
        title=title.strip()[:120],
        metric=metric,
        dimension=dimension,
        aggregation=aggregation,
        chart_type=chart_type,
        limit=limit,
    )


def execute_plan(dataframe: pd.DataFrame, plan: AnalysisPlan) -> pd.DataFrame:
    """Execute the validated plan using Pandas operations only."""
    if plan.chart_type == "histogram":
        return dataframe[[plan.metric]].dropna().copy()

    if plan.chart_type == "scatter":
        return dataframe[[plan.dimension, plan.metric]].dropna().copy()

    if plan.dimension is None:
        if plan.aggregation == "count":
            value = len(dataframe)
        else:
            value = getattr(dataframe[plan.metric], plan.aggregation)()
        return pd.DataFrame({"Result": [value]})

    if plan.aggregation == "count":
        result = (
            dataframe.groupby(plan.dimension, dropna=False)
            .size()
            .rename("Result")
            .reset_index()
        )
    else:
        result = (
            dataframe.groupby(plan.dimension, dropna=False)[plan.metric]
            .agg(plan.aggregation)
            .rename("Result")
            .reset_index()
        )

    result = result.sort_values("Result", ascending=False, kind="stable")
    return result.head(plan.limit).reset_index(drop=True)


def column_context(dataframe: pd.DataFrame) -> list[dict[str, str]]:
    """Return column names and types without exposing dataset rows."""
    return [
        {"name": str(column), "dtype": str(dtype)}
        for column, dtype in dataframe.dtypes.items()
    ]
