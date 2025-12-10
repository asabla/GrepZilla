"""Index writer for Meilisearch."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.src.config.logging import get_logger
from backend.src.services.ingestion.embed import EmbeddedChunk, EmbeddingResult
from backend.src.services.search.index_client import (
    CHUNKS_INDEX,
    MeilisearchClient,
    get_meilisearch_client,
)

logger = get_logger(__name__)


@dataclass
class IndexDocument:
    """Document to be indexed in Meilisearch."""

    id: str
    content: str
    repository_id: str
    repository_name: str
    branch_id: str
    branch_name: str
    file_path: str
    line_start: int
    line_end: int
    file_type: str
    chunk_index: int
    content_hash: str
    indexed_at: str
    embedding: list[float] | None = None
    start_index: int | None = None  # Character offset in original file
    end_index: int | None = None  # Character offset in original file
    chunking_mode: str = "token"  # Which chunker produced this chunk
    language: str | None = None  # Programming language (if detected)


@dataclass
class IndexWriteResult:
    """Result of an index write operation."""

    documents_indexed: int = 0
    documents_failed: int = 0
    errors: list[str] = field(default_factory=list)


class IndexWriter:
    """Write documents to Meilisearch index."""

    def __init__(
        self,
        client: MeilisearchClient | None = None,
        index_name: str | None = None,
    ):
        """Initialize index writer.

        Args:
            client: Meilisearch client instance.
            index_name: Name of the index to write to. Defaults to CHUNKS_INDEX.
        """
        self.client = client or get_meilisearch_client()
        self.index_name = index_name or CHUNKS_INDEX

    async def write_embedding_results(
        self,
        results: list[EmbeddingResult],
        repository_id: str,
        repository_name: str,
        branch_id: str,
        branch_name: str,
    ) -> IndexWriteResult:
        """Write embedding results to the index.

        Args:
            results: List of embedding results from processing.
            repository_id: Repository UUID.
            repository_name: Repository display name.
            branch_id: Branch UUID.
            branch_name: Branch name.

        Returns:
            IndexWriteResult with counts and errors.
        """
        write_result = IndexWriteResult()
        documents = []
        indexed_at = datetime.now(timezone.utc).isoformat()

        for result in results:
            if result.error:
                write_result.errors.append(
                    f"Skipping {result.file_path}: {result.error}"
                )
                continue

            for chunk in result.chunks:
                doc = self._create_document(
                    chunk=chunk,
                    repository_id=repository_id,
                    repository_name=repository_name,
                    branch_id=branch_id,
                    branch_name=branch_name,
                    indexed_at=indexed_at,
                )
                documents.append(doc)

        if not documents:
            logger.warning("No documents to index")
            return write_result

        # Write documents in batches
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            try:
                await self._write_batch(batch)
                write_result.documents_indexed += len(batch)
                logger.debug(
                    "Batch indexed",
                    batch_size=len(batch),
                    total_indexed=write_result.documents_indexed,
                )
            except Exception as e:
                write_result.documents_failed += len(batch)
                write_result.errors.append(f"Batch write failed: {e}")
                logger.error(
                    "Batch write failed",
                    batch_start=i,
                    batch_size=len(batch),
                    error=str(e),
                )

        logger.info(
            "Index write complete",
            documents_indexed=write_result.documents_indexed,
            documents_failed=write_result.documents_failed,
            errors=len(write_result.errors),
        )

        return write_result

    def _create_document(
        self,
        chunk: EmbeddedChunk,
        repository_id: str,
        repository_name: str,
        branch_id: str,
        branch_name: str,
        indexed_at: str,
    ) -> IndexDocument:
        """Create an index document from a chunk.

        Args:
            chunk: Embedded chunk.
            repository_id: Repository UUID.
            repository_name: Repository display name.
            branch_id: Branch UUID.
            branch_name: Branch name.
            indexed_at: Index timestamp.

        Returns:
            IndexDocument ready for indexing.
        """
        # Determine file type from extension
        extension = chunk.file_path.rsplit(".", 1)[-1] if "." in chunk.file_path else ""
        file_type = self._categorize_extension(extension)

        return IndexDocument(
            id=chunk.id,
            content=chunk.content,
            repository_id=repository_id,
            repository_name=repository_name,
            branch_id=branch_id,
            branch_name=branch_name,
            file_path=chunk.file_path,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            file_type=file_type,
            chunk_index=chunk.chunk_index,
            content_hash=chunk.content_hash,
            indexed_at=indexed_at,
            embedding=chunk.embedding,
            start_index=chunk.start_index,
            end_index=chunk.end_index,
            chunking_mode=chunk.chunking_mode,
            language=chunk.language,
        )

    def _categorize_extension(self, extension: str) -> str:
        """Categorize file extension into file type.

        Args:
            extension: File extension without dot.

        Returns:
            File type category.
        """
        code_exts = {
            "py",
            "js",
            "ts",
            "jsx",
            "tsx",
            "go",
            "rs",
            "java",
            "kt",
            "c",
            "cpp",
            "h",
            "cs",
            "rb",
            "php",
            "swift",
            "scala",
        }
        doc_exts = {"md", "rst", "txt", "adoc"}
        config_exts = {"json", "yaml", "yml", "toml", "ini", "cfg", "xml"}

        ext_lower = extension.lower()
        if ext_lower in code_exts:
            return "code"
        elif ext_lower in doc_exts:
            return "documentation"
        elif ext_lower in config_exts:
            return "configuration"
        else:
            return "other"

    async def _write_batch(self, documents: list[IndexDocument]) -> None:
        """Write a batch of documents to the index.

        Args:
            documents: Documents to write.

        Raises:
            Exception: If write fails.
        """
        # Convert to dicts for Meilisearch
        docs_dict = []
        for doc in documents:
            doc_dict = {
                "id": doc.id,
                "content": doc.content,
                "repository_id": doc.repository_id,
                "repository_name": doc.repository_name,
                "branch_id": doc.branch_id,
                "branch_name": doc.branch_name,
                "path": doc.file_path,
                "line_start": doc.line_start,
                "line_end": doc.line_end,
                "file_type": doc.file_type,
                "chunk_index": doc.chunk_index,
                "content_hash": doc.content_hash,
                "indexed_at": doc.indexed_at,
                "chunking_mode": doc.chunking_mode,
            }
            # Add optional fields only if they have values
            if doc.start_index is not None:
                doc_dict["start_index"] = doc.start_index
            if doc.end_index is not None:
                doc_dict["end_index"] = doc.end_index
            if doc.language:
                doc_dict["language"] = doc.language
            if doc.embedding:
                doc_dict["_vectors"] = {"default": doc.embedding}
            docs_dict.append(doc_dict)

        # Write to Meilisearch
        await self.client.add_documents(self.index_name, docs_dict)

    async def delete_branch_documents(
        self,
        repository_id: str,
        branch_id: str,
    ) -> int:
        """Delete all documents for a branch (before reindex).

        Args:
            repository_id: Repository UUID.
            branch_id: Branch UUID.

        Returns:
            Number of documents deleted.
        """
        logger.info(
            "Deleting branch documents",
            repository_id=repository_id,
            branch_id=branch_id,
        )

        # Use filter to delete matching documents
        filter_str = f"repository_id = '{repository_id}' AND branch_id = '{branch_id}'"
        deleted = await self.client.delete_documents_by_filter(
            self.index_name, filter_str
        )

        logger.info(
            "Branch documents deleted",
            repository_id=repository_id,
            branch_id=branch_id,
            deleted_count=deleted,
        )

        return deleted

    # =========================================================================
    # Synchronous methods for Celery workers
    # =========================================================================

    def write_embedding_results_sync(
        self,
        results: list[EmbeddingResult],
        repository_id: str,
        repository_name: str,
        branch_id: str,
        branch_name: str,
    ) -> IndexWriteResult:
        """Write embedding results to the index (synchronous version).

        Args:
            results: List of embedding results from processing.
            repository_id: Repository UUID.
            repository_name: Repository display name.
            branch_id: Branch UUID.
            branch_name: Branch name.

        Returns:
            IndexWriteResult with counts and errors.
        """
        write_result = IndexWriteResult()
        documents = []
        indexed_at = datetime.now(timezone.utc).isoformat()

        for result in results:
            if result.error:
                write_result.errors.append(
                    f"Skipping {result.file_path}: {result.error}"
                )
                continue

            for chunk in result.chunks:
                doc = self._create_document(
                    chunk=chunk,
                    repository_id=repository_id,
                    repository_name=repository_name,
                    branch_id=branch_id,
                    branch_name=branch_name,
                    indexed_at=indexed_at,
                )
                documents.append(doc)

        if not documents:
            logger.warning("No documents to index (sync)")
            return write_result

        # Write documents in batches
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            try:
                self._write_batch_sync(batch)
                write_result.documents_indexed += len(batch)
                logger.debug(
                    "Batch indexed (sync)",
                    batch_size=len(batch),
                    total_indexed=write_result.documents_indexed,
                )
            except Exception as e:
                write_result.documents_failed += len(batch)
                write_result.errors.append(f"Batch write failed: {e}")
                logger.error(
                    "Batch write failed (sync)",
                    batch_start=i,
                    batch_size=len(batch),
                    error=str(e),
                )

        logger.info(
            "Index write complete (sync)",
            documents_indexed=write_result.documents_indexed,
            documents_failed=write_result.documents_failed,
            errors=len(write_result.errors),
        )

        return write_result

    def _write_batch_sync(self, documents: list[IndexDocument]) -> None:
        """Write a batch of documents to the index (synchronous).

        Args:
            documents: Documents to write.

        Raises:
            Exception: If write fails.
        """
        # Convert to dicts for Meilisearch
        docs_dict = []
        for doc in documents:
            doc_dict = {
                "id": doc.id,
                "content": doc.content,
                "repository_id": doc.repository_id,
                "repository_name": doc.repository_name,
                "branch_id": doc.branch_id,
                "branch_name": doc.branch_name,
                "path": doc.file_path,
                "line_start": doc.line_start,
                "line_end": doc.line_end,
                "file_type": doc.file_type,
                "chunk_index": doc.chunk_index,
                "content_hash": doc.content_hash,
                "indexed_at": doc.indexed_at,
                "chunking_mode": doc.chunking_mode,
            }
            # Add optional fields only if they have values
            if doc.start_index is not None:
                doc_dict["start_index"] = doc.start_index
            if doc.end_index is not None:
                doc_dict["end_index"] = doc.end_index
            if doc.language:
                doc_dict["language"] = doc.language
            if doc.embedding:
                doc_dict["_vectors"] = {"default": doc.embedding}
            docs_dict.append(doc_dict)

        # Write to Meilisearch
        self.client.add_documents_sync(self.index_name, docs_dict)

    def delete_branch_documents_sync(
        self,
        repository_id: str,
        branch_id: str,
    ) -> int:
        """Delete all documents for a branch (synchronous version).

        Args:
            repository_id: Repository UUID.
            branch_id: Branch UUID.

        Returns:
            Number of documents deleted.
        """
        logger.info(
            "Deleting branch documents (sync)",
            repository_id=repository_id,
            branch_id=branch_id,
        )

        # Use filter to delete matching documents
        filter_str = f"repository_id = '{repository_id}' AND branch_id = '{branch_id}'"
        deleted = self.client.delete_documents_by_filter_sync(
            self.index_name, filter_str
        )

        logger.info(
            "Branch documents deleted (sync)",
            repository_id=repository_id,
            branch_id=branch_id,
            deleted_count=deleted,
        )

        return deleted


# Service singleton
_index_writer: IndexWriter | None = None


def get_index_writer() -> IndexWriter:
    """Get index writer singleton."""
    global _index_writer
    if _index_writer is None:
        _index_writer = IndexWriter()
    return _index_writer
