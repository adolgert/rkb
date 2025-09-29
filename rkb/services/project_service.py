"""Project service for managing document collections and experiments."""

import datetime
import json
import logging
from pathlib import Path
from typing import Any

from rkb.core.document_registry import DocumentRegistry
from rkb.core.models import Document, DocumentStatus, ProjectStats

LOGGER = logging.getLogger("rkb.services.project_service")


class ProjectService:
    """Service for managing projects and document collections."""

    def __init__(self, registry: DocumentRegistry | None = None):
        """Initialize project service.

        Args:
            registry: Document registry for project management
        """
        self.registry = registry or DocumentRegistry()

    def create_project(
        self,
        project_name: str,
        description: str = "",
        data_dir: str | Path | None = None,
    ) -> str:
        """Create a new project.

        Args:
            project_name: Name of the project
            description: Project description
            data_dir: Optional data directory for the project

        Returns:
            Project ID
        """
        project_id = f"project_{int(datetime.datetime.now().timestamp())}"

        # For now, projects are just logical groupings in the registry
        # Future versions could have a dedicated projects table

        LOGGER.info(f"Created project '{project_name}' with ID: {project_id}")
        if description:
            LOGGER.debug(f"  Description: {description}")
        if data_dir:
            LOGGER.debug(f"  Data directory: {data_dir}")

        return project_id

    def list_projects(self) -> dict[str, ProjectStats]:
        """List all projects and their statistics.

        Returns:
            Dictionary mapping project IDs to ProjectStats
        """
        # Get all documents and group by project_id
        self.registry.get_processing_stats()  # Ensure registry is accessible

        # For now, we'll identify projects by looking at project_id attributes
        # This is a simplified approach - future versions could have a projects table
        projects = {}

        # Get documents by different statuses to build project stats
        for status in DocumentStatus:
            docs = self.registry.get_documents_by_status(status)
            for doc in docs:
                project_id = getattr(doc, "project_id", "default")
                if project_id not in projects:
                    projects[project_id] = {
                        "total_count": 0,
                        "pending_count": 0,
                        "extracting_count": 0,
                        "extracted_count": 0,
                        "indexing_count": 0,
                        "indexed_count": 0,
                        "failed_count": 0,
                    }

                projects[project_id]["total_count"] += 1
                status_key = f"{status.value}_count"
                if status_key in projects[project_id]:
                    projects[project_id][status_key] += 1

        # Convert to ProjectStats objects
        project_stats = {}
        for project_id, stats in projects.items():
            project_stats[project_id] = ProjectStats(
                project_id=project_id,
                total_documents=stats["total_count"],
                pending_count=stats["pending_count"],
                extracting_count=stats["extracting_count"],
                extracted_count=stats["extracted_count"],
                indexing_count=stats["indexing_count"],
                indexed_count=stats["indexed_count"],
                failed_count=stats["failed_count"],
                total_chunks=0,  # Would need to calculate from embeddings
            )

        return project_stats

    def get_project_documents(
        self,
        project_id: str,
        status: DocumentStatus | None = None,
    ) -> list[Document]:
        """Get documents for a specific project.

        Args:
            project_id: Project identifier
            status: Optional status filter

        Returns:
            List of documents in the project
        """
        if status:
            # Get documents by status and filter by project
            all_docs = self.registry.get_documents_by_status(status)
            return [doc for doc in all_docs if getattr(doc, "project_id", None) == project_id]
        return self.registry.get_documents_by_project(project_id)

    def find_recent_pdfs(
        self,
        data_dir: str | Path,
        num_files: int = 50,
        output_file: str | Path | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find the most recent PDF files based on modification time.

        Args:
            data_dir: Directory to search for PDFs
            num_files: Maximum number of files to return
            output_file: Optional path to save file list as JSON
            project_id: Optional project ID to associate files with

        Returns:
            List of file information dictionaries
        """
        data_path = Path(data_dir)
        if not data_path.exists():
            raise FileNotFoundError(f"Data directory not found: {data_path}")

        LOGGER.info(f"Scanning for PDFs in: {data_path} (including subdirectories)")

        # Find all PDF files recursively in subdirectories
        pdf_files = list(data_path.glob("**/*.pdf"))

        if not pdf_files:
            raise FileNotFoundError(f"No PDF files found in {data_path} or its subdirectories")

        LOGGER.info(f"Found {len(pdf_files)} PDF files in directory tree")

        # Get file info with modification time
        file_info = []
        for pdf_file in pdf_files:
            try:
                stat = pdf_file.stat()
                file_info.append({
                    "path": str(pdf_file),
                    "name": pdf_file.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified_time": stat.st_mtime,
                    "modified_date": datetime.datetime.fromtimestamp(
                        stat.st_mtime, tz=datetime.UTC
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                    "project_id": project_id,
                })
            except Exception as e:
                LOGGER.warning(f"Error reading {pdf_file}: {e}")
                continue

        # Sort by modification time (most recent first)
        file_info.sort(key=lambda x: x["modified_time"], reverse=True)

        # Take the most recent files
        recent_files = file_info[:num_files]

        LOGGER.info(f"Selected {len(recent_files)} most recent files:")
        if recent_files:
            newest = recent_files[0]
            LOGGER.debug(f"   Newest: {newest['name']} ({newest['modified_date']})")
            if len(recent_files) > 1:
                oldest = recent_files[-1]
                LOGGER.debug(f"   Oldest: {oldest['name']} ({oldest['modified_date']})")

        # Calculate total size
        total_size = sum(file["size_mb"] for file in recent_files)
        LOGGER.info(f"Total size: {total_size:.1f} MB")

        # Save to JSON file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w") as f:
                json.dump(recent_files, f, indent=2)

            LOGGER.info(f"Saved file list to: {output_path}")

        return recent_files

    def create_document_subset(
        self,
        subset_name: str,
        criteria: dict[str, Any],
        project_id: str | None = None,
    ) -> list[Document]:
        """Create a subset of documents based on criteria.

        Args:
            subset_name: Name for the document subset
            criteria: Selection criteria (e.g., date range, keywords, status)
            project_id: Optional project ID to filter by

        Returns:
            List of documents matching criteria
        """
        LOGGER.info(f"Creating document subset '{subset_name}' with criteria: {criteria}")

        # Start with all documents or project documents
        if project_id:
            documents = self.get_project_documents(project_id)
        else:
            # For now, get documents from all projects
            # In future, could have a method to get all documents
            documents = []
            for status in DocumentStatus:
                documents.extend(self.registry.get_documents_by_status(status))

        # Apply filters based on criteria
        filtered_docs = documents

        # Filter by status
        if "status" in criteria:
            target_status = DocumentStatus(criteria["status"])
            filtered_docs = [doc for doc in filtered_docs if doc.status == target_status]

        # Filter by date range
        if "date_from" in criteria:
            date_from = datetime.fromisoformat(criteria["date_from"])
            filtered_docs = [doc for doc in filtered_docs if doc.added_date >= date_from]

        if "date_to" in criteria:
            date_to = datetime.fromisoformat(criteria["date_to"])
            filtered_docs = [doc for doc in filtered_docs if doc.added_date <= date_to]

        # Filter by filename patterns
        if "filename_pattern" in criteria:
            pattern = criteria["filename_pattern"].lower()
            filtered_docs = [
                doc for doc in filtered_docs
                if doc.source_path and pattern in doc.source_path.name.lower()
            ]

        # Filter by file size
        if "max_size_mb" in criteria and "min_size_mb" in criteria:
            max_size = criteria["max_size_mb"] * 1024 * 1024  # Convert to bytes
            min_size = criteria["min_size_mb"] * 1024 * 1024
            size_filtered = []
            for doc in filtered_docs:
                if doc.source_path and doc.source_path.exists():
                    size = doc.source_path.stat().st_size
                    if min_size <= size <= max_size:
                        size_filtered.append(doc)
            filtered_docs = size_filtered

        # Sort by criteria
        sort_by = criteria.get("sort_by", "added_date")
        reverse = criteria.get("sort_desc", True)

        if sort_by == "added_date":
            filtered_docs.sort(key=lambda x: x.added_date, reverse=reverse)
        elif sort_by == "filename":
            filtered_docs.sort(
                key=lambda x: x.source_path.name if x.source_path else "",
                reverse=reverse,
            )

        # Limit results
        if "limit" in criteria:
            filtered_docs = filtered_docs[:criteria["limit"]]

        LOGGER.info(f"Found {len(filtered_docs)} documents matching criteria")

        # Could save subset definition for future use
        # subset_info would contain: subset_name, criteria, project_id, created_date,
        # document_count, document_ids

        return filtered_docs

    def get_project_stats(self, project_id: str) -> ProjectStats:
        """Get detailed statistics for a specific project.

        Args:
            project_id: Project identifier

        Returns:
            ProjectStats with detailed information
        """
        documents = self.get_project_documents(project_id)

        # Count by status
        status_counts = {}
        for status in DocumentStatus:
            status_counts[status.value] = sum(1 for doc in documents if doc.status == status)

        # Get processing stats from registry
        registry_stats = self.registry.get_processing_stats()

        return ProjectStats(
            project_id=project_id,
            total_documents=len(documents),
            pending_count=status_counts.get("pending", 0),
            extracting_count=status_counts.get("extracting", 0),
            extracted_count=status_counts.get("extracted", 0),
            indexing_count=status_counts.get("indexing", 0),
            indexed_count=status_counts.get("indexed", 0),
            failed_count=status_counts.get("failed", 0),
            total_chunks=registry_stats.get("total_chunks_embedded", 0),
        )

    def export_project_data(
        self,
        project_id: str,
        output_file: str | Path,
        include_content: bool = False,
    ) -> dict[str, Any]:
        """Export project data to JSON file.

        Args:
            project_id: Project identifier
            output_file: Path to output JSON file
            include_content: Whether to include extracted content

        Returns:
            Summary of exported data
        """
        documents = self.get_project_documents(project_id)
        stats = self.get_project_stats(project_id)

        export_data = {
            "project_id": project_id,
            "export_date": datetime.datetime.now().isoformat(),
            "stats": {
                "total_documents": stats.total_documents,
                "indexed_count": stats.indexed_count,
                "failed_count": stats.failed_count,
            },
            "documents": [],
        }

        for doc in documents:
            doc_data = {
                "doc_id": doc.doc_id,
                "source_path": str(doc.source_path) if doc.source_path else None,
                "title": doc.title,
                "authors": doc.authors,
                "status": doc.status.value,
                "added_date": doc.added_date.isoformat(),
            }

            # Add content if requested (this would require reading from extractions)
            if include_content:
                # Would need to implement extraction content retrieval
                doc_data["content"] = None  # Placeholder

            export_data["documents"].append(doc_data)

        # Save to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as f:
            json.dump(export_data, f, indent=2)

        LOGGER.info(f"Exported project data to: {output_path}")
        LOGGER.debug(f"  Documents: {len(documents)}")
        LOGGER.debug(f"  Size: {output_path.stat().st_size / 1024:.1f} KB")

        return {
            "output_file": str(output_path),
            "documents_exported": len(documents),
            "file_size_kb": round(output_path.stat().st_size / 1024, 1),
        }
