import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.database import adapt_query, connect, uses_postgres


class DatabaseConnectionTests(unittest.TestCase):
    def test_postgres_detection_requires_a_non_empty_url(self):
        self.assertFalse(uses_postgres(""))
        self.assertFalse(uses_postgres("   "))
        self.assertTrue(uses_postgres("postgresql://example"))

    def test_query_placeholders_are_adapted_only_for_postgres(self):
        query = "SELECT * FROM papers WHERE pmid = ? AND pub_year >= ?"
        self.assertEqual(adapt_query(query, ""), query)
        self.assertEqual(
            adapt_query(query, "postgresql://example"),
            "SELECT * FROM papers WHERE pmid = %s AND pub_year >= %s",
        )

    @patch("psycopg.connect")
    def test_postgres_connection_disables_prepared_statements(self, mock_connect):
        connection = MagicMock()
        mock_connect.return_value.__enter__.return_value = connection

        with connect("postgresql://example", Path("unused.db")) as result:
            self.assertIs(result, connection)

        self.assertIsNone(mock_connect.call_args.kwargs["prepare_threshold"])


if __name__ == "__main__":
    unittest.main()
