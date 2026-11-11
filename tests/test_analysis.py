import unittest

import pandas as pd

from analysis import execute_plan, validate_plan


class AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataframe = pd.DataFrame(
            {
                "region": ["South", "North", "South"],
                "sales": [100, 50, 75],
                "units": [2, 1, 3],
            }
        )

    def test_grouped_sum_orders_results(self) -> None:
        plan = validate_plan(
            {
                "title": "Sales by region",
                "metric": "sales",
                "dimension": "region",
                "aggregation": "sum",
                "chart_type": "bar",
                "limit": 10,
            },
            self.dataframe,
        )

        result = execute_plan(self.dataframe, plan)

        self.assertEqual(result["region"].tolist(), ["South", "North"])
        self.assertEqual(result["Result"].tolist(), [175, 50])

    def test_count_without_dimension_returns_row_count(self) -> None:
        plan = validate_plan(
            {
                "title": "Record count",
                "metric": None,
                "dimension": None,
                "aggregation": "count",
                "chart_type": "metric",
                "limit": 10,
            },
            self.dataframe,
        )

        result = execute_plan(self.dataframe, plan)

        self.assertEqual(result.iloc[0, 0], 3)

    def test_unknown_column_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not exist"):
            validate_plan(
                {
                    "title": "Sales by region",
                    "metric": "unknown_value",
                    "dimension": "region",
                    "aggregation": "sum",
                    "chart_type": "bar",
                    "limit": 10,
                },
                self.dataframe,
            )

    def test_non_numeric_metric_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "is not numeric"):
            validate_plan(
                {
                    "title": "Records by region",
                    "metric": "region",
                    "dimension": "region",
                    "aggregation": "sum",
                    "chart_type": "bar",
                    "limit": 10,
                },
                self.dataframe,
            )


if __name__ == "__main__":
    unittest.main()
