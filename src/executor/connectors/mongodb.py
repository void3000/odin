"""
MongoDB connector implementation.

Wraps pymongo driver and implements DatabaseConnector protocol.
"""

from typing import Any, List, Tuple, Optional

from ..connector import DatabaseConnector, RawResult
from ..errors import (
    ConnectionError as DBConnectionError,
    QueryError,
    TransactionError
)


class MongoDBConnector:
    """
    MongoDB connector using pymongo.

    Implements DatabaseConnector protocol for MongoDB databases.

    Features:
    - Connection management
    - Query execution (find, filter, projection, sort, limit)
    - Transaction support (multi-document transactions in replica sets)
    - Error translation from pymongo to common exceptions

    Note: MongoDB query format expected:
    {
        "collection": "users",
        "filter": {"status": "active"},
        "projection": {"name": 1, "email": 1, "_id": 0},
        "sort": [("created_at", -1)],
        "limit": 10
    }
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        host: str = "localhost",
        port: int = 27017,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """Initialize MongoDB connector.

        Can use either connection_string OR individual parameters.

        Args:
            connection_string: MongoDB connection string
                (e.g., "mongodb://user:pass@localhost:27017/db")
            host: Database host (default localhost)
            port: Database port (default 27017)
            database: Database name
            username: Username for authentication
            password: Password for authentication

        Raises:
            ValueError: If neither connection_string nor database provided
        """
        if connection_string:
            self.connection_string = connection_string
            # Extract database name from connection string if not provided
            if not database and "/" in connection_string:
                self.database_name = connection_string.split("/")[-1].split("?")[0]
            else:
                self.database_name = database
        elif database:
            # Build connection string from parameters
            if username and password:
                auth = f"{username}:{password}@"
            else:
                auth = ""
            self.connection_string = f"mongodb://{auth}{host}:{port}"
            self.database_name = database
        else:
            raise ValueError(
                "Must provide either connection_string or database name"
            )

        self.client = None
        self.db = None
        self._session = None
        self._in_transaction = False

    def connect(self) -> None:
        """Establish MongoDB connection.

        Raises:
            ConnectionError: If connection fails
        """
        try:
            import pymongo
            self.client = pymongo.MongoClient(self.connection_string)

            # Test connection
            self.client.admin.command("ping")

            # Get database
            self.db = self.client[self.database_name]

        except ImportError:
            raise DBConnectionError(
                "pymongo not installed. Install with: pip install pymongo"
            )
        except Exception as e:
            raise DBConnectionError(
                f"Failed to connect to MongoDB: {str(e)}",
                original=e
            )

    def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._session:
            try:
                self._session.end_session()
            except Exception:
                pass
            self._session = None

        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
            self.db = None

        self._in_transaction = False

    def is_connected(self) -> bool:
        """Check if connected to MongoDB.

        Returns:
            True if connection is active
        """
        if not self.client:
            return False

        try:
            # Test connection with ping
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def execute_query(self, query: Any, params: List[Any] = None) -> RawResult:
        """Execute single MongoDB query.

        Args:
            query: MongoDB query structure (dict) with:
                - collection: collection name
                - filter: query filter dict
                - projection: projection dict (optional)
                - sort: sort list of tuples (optional)
                - limit: limit int (optional)
            params: Unused for MongoDB (kept for compatibility)

        Returns:
            RawResult with rows, columns, rowcount

        Raises:
            ConnectionError: If not connected
            QueryError: If query execution fails
        """
        if not self.client or not self.db:
            raise DBConnectionError("Not connected to database")

        try:
            # Extract query parameters
            if isinstance(query, dict):
                # New format: GenericQueryResult.query
                if "collection" in query:
                    mongo_query = query
                # Old format: {"query": {...}}
                elif "query" in query:
                    mongo_query = query["query"]
                else:
                    raise QueryError(
                        "Invalid query format",
                        str(query),
                        params or []
                    )
            else:
                raise QueryError(
                    "MongoDB query must be a dict",
                    str(query),
                    params or []
                )

            collection_name = mongo_query["collection"]
            filter_dict = mongo_query.get("filter", {})
            projection = mongo_query.get("projection")
            sort = mongo_query.get("sort")
            limit = mongo_query.get("limit")

            # Get collection
            collection = self.db[collection_name]

            # Build cursor
            cursor = collection.find(filter_dict, projection)

            # Apply sort
            if sort:
                cursor = cursor.sort(sort)

            # Apply limit
            if limit:
                cursor = cursor.limit(limit)

            # Fetch documents
            documents = list(cursor)

            # Convert to RawResult format
            return self._to_raw_result(documents, projection)

        except DBConnectionError:
            raise

        except QueryError:
            raise

        except Exception as e:
            # Translate pymongo errors to common exceptions
            error_msg = str(e)

            # Check if it's a connection error
            if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                raise DBConnectionError(
                    f"Connection lost during query execution: {error_msg}",
                    original=e
                )

            # Otherwise it's a query error
            raise QueryError(
                message=f"Query execution failed: {error_msg}",
                sql=str(mongo_query),
                params=params or [],
                original=e
            )

    def execute_many(
        self,
        queries: List[Tuple[Any, List[Any]]]
    ) -> List[RawResult]:
        """Execute multiple MongoDB queries sequentially.

        Args:
            queries: List of (query, params) tuples

        Returns:
            List of RawResult, one per query

        Raises:
            ConnectionError: If not connected
            QueryError: If any query fails
        """
        results = []

        for query, params in queries:
            result = self.execute_query(query, params)
            results.append(result)

        return results

    def begin_transaction(self) -> None:
        """Start MongoDB transaction.

        Note: Requires MongoDB replica set or sharded cluster.

        Raises:
            TransactionError: If transaction cannot be started
            ConnectionError: If not connected
        """
        if not self.client:
            raise DBConnectionError("Not connected to database")

        if self._in_transaction:
            raise TransactionError("Transaction already in progress")

        try:
            self._session = self.client.start_session()
            self._session.start_transaction()
            self._in_transaction = True

        except Exception as e:
            raise TransactionError(
                f"Failed to begin transaction: {str(e)}. "
                f"Note: Transactions require MongoDB replica set or sharded cluster.",
                original=e
            )

    def commit(self) -> None:
        """Commit MongoDB transaction.

        Raises:
            TransactionError: If commit fails
            ConnectionError: If not connected
        """
        if not self.client:
            raise DBConnectionError("Not connected to database")

        if not self._in_transaction or not self._session:
            raise TransactionError("No transaction active")

        try:
            self._session.commit_transaction()
            self._session.end_session()
            self._session = None
            self._in_transaction = False

        except Exception as e:
            raise TransactionError(
                f"Failed to commit transaction: {str(e)}",
                original=e
            )

    def rollback(self) -> None:
        """Rollback MongoDB transaction.

        Safe to call even if no transaction is active.

        Raises:
            TransactionError: If rollback fails
            ConnectionError: If not connected
        """
        if not self.client:
            raise DBConnectionError("Not connected to database")

        if self._session:
            try:
                if self._in_transaction:
                    self._session.abort_transaction()
                self._session.end_session()
            except Exception as e:
                raise TransactionError(
                    f"Failed to rollback transaction: {str(e)}",
                    original=e
                )
            finally:
                self._session = None
                self._in_transaction = False

    def get_metadata(self) -> dict:
        """Get MongoDB connector metadata.

        Returns:
            Dictionary with connector information
        """
        metadata = {
            "database_type": "mongodb",
            "driver": "pymongo",
            "version": None,
            "connected": self.is_connected(),
            "database": self.database_name
        }

        if self.is_connected():
            try:
                server_info = self.client.server_info()
                metadata["version"] = server_info.get("version")
            except Exception:
                pass

        return metadata

    def _to_raw_result(
        self,
        documents: List[dict],
        projection: Optional[dict]
    ) -> RawResult:
        """Convert MongoDB documents to RawResult format.

        Args:
            documents: List of MongoDB documents (dicts)
            projection: Projection dict (for column extraction)

        Returns:
            RawResult with rows as tuples
        """
        if not documents:
            return RawResult(rows=[], columns=[], rowcount=0)

        # Extract columns from projection or first document
        if projection:
            # Use projection keys (excluding _id if it's 0)
            columns = [k for k, v in projection.items() if k != "_id" or v == 1]
        else:
            # Use keys from first document
            columns = [k for k in documents[0].keys() if k != "_id"]

        # Convert documents to tuples
        rows = [
            tuple(doc.get(col) for col in columns)
            for doc in documents
        ]

        return RawResult(
            rows=rows,
            columns=columns,
            rowcount=len(rows)
        )
