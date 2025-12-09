"""Constants for file size limits and performance budgets."""

from typing import Final

# =============================================================================
# File Processing Limits
# =============================================================================

# Maximum file size to fully parse and index (25 MB)
MAX_FILE_SIZE_BYTES: Final[int] = 25 * 1024 * 1024

# Files larger than this are cataloged but not parsed for text search
CATALOG_ONLY_SIZE_THRESHOLD: Final[int] = MAX_FILE_SIZE_BYTES

# Maximum number of files to process in a single ingestion batch
MAX_BATCH_SIZE: Final[int] = 100

# Maximum file path length to index
MAX_PATH_LENGTH: Final[int] = 512


# =============================================================================
# Chunking Configuration
# =============================================================================

# Target chunk size in tokens for embedding
CHUNK_SIZE_TOKENS: Final[int] = 512

# Overlap between chunks in tokens
CHUNK_OVERLAP_TOKENS: Final[int] = 64

# Maximum chunks per file (to prevent excessive memory usage)
MAX_CHUNKS_PER_FILE: Final[int] = 1000


# =============================================================================
# Performance Budgets
# =============================================================================

# Query latency targets (milliseconds)
QUERY_P95_LATENCY_MS: Final[int] = 3000  # 3 seconds for p95

# Freshness targets
NOTIFICATION_TO_INDEX_MINUTES: Final[int] = 10  # 90% within 10 minutes
SCHEDULED_REINDEX_HOURS: Final[int] = 24  # Daily reindex
FRESHNESS_STALE_THRESHOLD_HOURS: Final[int] = 48  # Mark stale after 48 hours

# Backlog thresholds
BACKLOG_WARNING_THRESHOLD: Final[int] = 50
BACKLOG_CRITICAL_THRESHOLD: Final[int] = 100


# =============================================================================
# API Limits
# =============================================================================

# Maximum query length
MAX_QUERY_LENGTH: Final[int] = 2000

# Maximum repositories per query scope
MAX_REPOS_PER_QUERY: Final[int] = 20

# Maximum results to return
MAX_SEARCH_RESULTS: Final[int] = 50
DEFAULT_SEARCH_RESULTS: Final[int] = 10

# Maximum citations to include in response
MAX_CITATIONS: Final[int] = 20


# =============================================================================
# Repository Limits
# =============================================================================

# Maximum repository size to index
MAX_REPO_SIZE_GB: Final[int] = 5

# Maximum active repositories
MAX_ACTIVE_REPOS: Final[int] = 50

# Maximum branches to track per repository
MAX_BRANCHES_PER_REPO: Final[int] = 20


# =============================================================================
# File Types
# =============================================================================

# File extensions to parse as code
CODE_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".kt",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala",
    ".sh", ".bash", ".zsh", ".sql", ".r", ".m", ".pl", ".lua", ".vim",
})

# File extensions to parse as documentation
DOC_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".md", ".rst", ".txt", ".adoc", ".tex", ".html", ".htm",
})

# File extensions to parse as configuration
CONFIG_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml", ".properties", ".env",
})

# File extensions to skip entirely (binary/media)
BINARY_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pyc", ".pyo", ".class", ".o", ".obj",
})

# Directories to skip during ingestion
SKIP_DIRECTORIES: Final[frozenset[str]] = frozenset({
    ".git", ".svn", ".hg", ".bzr",
    "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "target", "out", "bin", "obj",
    ".idea", ".vscode", ".vs",
    "vendor", "packages",
})
