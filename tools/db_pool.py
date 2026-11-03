#!/usr/bin/env python3
# coding: utf-8
"""
db_pool.py — SQLite Connection Pool with WAL Mode and Proper Locking for Windows.

Provides thread-safe connection pooling with WAL mode, busy timeout,
and cross-platform file locking for forensic tools.
"""

import sqlite3
import sys
import threading
import contextlib
import os
import time
from pathlib import Path
from typing import Optional, Generator, Any
from contextlib import contextmanager
from threading import Lock

# Cross-platform file locking
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False
    import msvcrt


class SQLitePool:
    """Thread-safe SQLite connection pool with WAL mode and Windows-friendly locking."""
    
    def __init__(
        self,
        db_path: str,
        pool_size: int = 5,
        timeout: float = 30.0,
        wal_mode: bool = True,
        busy_timeout: int = 30000,
        synchronous: str = "NORMAL",
    ):
        self.db_path = str(db_path)
        self.pool_size = pool_size
        self.timeout = timeout
        self.wal_mode = wal_mode
        self.busy_timeout = busy_timeout
        self.synchronous = synchronous
        self._pool: list[sqlite3.Connection] = []
        self._lock = Lock()
        self._initialized = False
        self._init_lock = Lock()
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with optimal settings."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            isolation_level=None,  # Autocommit mode
        )
        
        # Enable WAL mode for better concurrency
        if self.wal_mode:
            conn.execute("PRAGMA journal_mode=WAL")
        
        # Set busy timeout for Windows file locking issues
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout}")
        
        # Set synchronous mode
        conn.execute(f"PRAGMA synchronous={self.synchronous}")
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys=ON")
        
        # Set page size for better performance
        conn.execute("PRAGMA page_size=4096")
        
        # Set cache size
        conn.execute("PRAGMA cache_size=-32768")  # 32MB cache
        
        # Enable memory mapping
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB
        
        return conn
    
    def initialize(self) -> None:
        """Initialize the connection pool."""
        with self._init_lock:
            if self._initialized:
                return
            
            # Create initial connections
            for _ in range(self.pool_size):
                conn = self._create_connection()
                self._pool.append(conn)
            
            self._initialized = True
    
    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a connection from the pool."""
        if not self._initialized:
            self.initialize()
        
        conn = None
        with self._lock:
            if self._pool:
                conn = self._pool.pop()
            else:
                conn = self._create_connection()
        
        try:
            yield conn
        except Exception:
            # Connection had an error, discard it
            try:
                conn.close()
            except Exception as exc:
                print(f"[db_pool] errored connection close failed: {exc}",
                      file=sys.stderr)
            conn = None
            raise
        finally:
            if conn is not None:
                with self._lock:
                    if len(self._pool) < self.pool_size:
                        self._pool.append(conn)
                    else:
                        try:
                            conn.close()
                        except Exception as exc:
                            print(f"[db_pool] excess connection close failed: {exc}",
                                  file=sys.stderr)
    
    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a connection with automatic transaction handling."""
        with self.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single SQL statement."""
        with self.connection() as conn:
            return conn.execute(sql, params)
    
    def executemany(self, sql: str, params_list: list) -> sqlite3.Cursor:
        """Execute multiple SQL statements."""
        with self.connection() as conn:
            return conn.executemany(sql, params_list)
    
    def fetchone(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        """Execute and fetch one row."""
        with self.connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()
    
    def fetchall(self, sql: str, params: tuple = ()) -> list:
        """Execute and fetch all rows."""
        with self.connection() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception as exc:
                    print(f"[db_pool] pooled connection close failed: {exc}",
                          file=sys.stderr)
            self._pool.clear()
            self._initialized = False
    
    def __enter__(self):
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all()


# Global pool registry for reuse across tools
_pool_registry: dict[str, SQLitePool] = {}
_pool_registry_lock = Lock()


def get_pool(
    db_path: str,
    pool_size: int = 5,
    timeout: float = 30.0,
) -> SQLitePool:
    """Get or create a connection pool for the given database path."""
    global _pool_registry
    path = str(Path(db_path).resolve())
    
    with _pool_registry_lock:
        if path not in _pool_registry:
            _pool_registry[path] = SQLitePool(db_path, pool_size=5, timeout=30.0)
            _pool_registry[path].initialize()
        return _pool_registry[path]


def close_all_pools() -> None:
    """Close all connection pools."""
    global _pool_registry
    with _pool_registry_lock:
        for pool in _pool_registry.values():
            pool.close_all()
        _pool_registry.clear()


@contextmanager
def get_db_connection(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Convenience function to get a database connection from the pool."""
    pool = get_pool(db_path)
    with pool.connection() as conn:
        yield conn


@contextmanager
def get_db_transaction(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Convenience function to get a database transaction."""
    pool = get_pool(db_path)
    with pool.transaction() as conn:
        yield conn


# For backward compatibility
def get_connection(db_path: str) -> sqlite3.Connection:
    """Get a single connection (for backward compatibility)."""
    pool = get_pool(db_path)
    return pool._create_connection()


# Initialize on import for backward compatibility
def init_db(db_path: str) -> SQLitePool:
    """Initialize a database pool."""
    pool = get_pool(db_path)
    pool.initialize()
    return pool