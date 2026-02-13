from __future__ import annotations

import argparse
import logging
import sys

from ingest.config import IngestConfig
from ingest.pipeline import IngestPipeline
from ingest.project_manager import ProjectManager
from ingest.retriever import Retriever
from ingest.store import ProjectStore


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        prog="meeting-buddy-ingest",
        description="Meeting Buddy document ingestion CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create-project
    p_create = sub.add_parser("create-project", help="Create a new project")
    p_create.add_argument("--name", required=True, help="Project display name")

    # list-projects
    sub.add_parser("list-projects", help="List all projects")

    # delete-project
    p_del_proj = sub.add_parser("delete-project", help="Delete a project")
    p_del_proj.add_argument("--name", required=True, help="Project name")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest files into a project")
    p_ingest.add_argument("--project", required=True, help="Project name")
    p_ingest.add_argument("--path", required=True, help="File or directory path")
    p_ingest.add_argument("--recursive", action="store_true", default=True)

    # list-docs
    p_docs = sub.add_parser("list-docs", help="List documents in a project")
    p_docs.add_argument("--project", required=True, help="Project name")

    # delete-doc
    p_del = sub.add_parser("delete-doc", help="Delete a document from a project")
    p_del.add_argument("--project", required=True, help="Project name")
    p_del.add_argument("--title", required=True, help="Document title")

    # search
    p_search = sub.add_parser("search", help="Search a project")
    p_search.add_argument("--project", required=True, help="Project name")
    p_search.add_argument("--query", required=True, help="Search query")
    p_search.add_argument("--top-k", type=int, default=5, help="Number of results")

    args = parser.parse_args(argv)
    config = IngestConfig()
    manager = ProjectManager(config.project)

    if args.command == "create-project":
        path = manager.create_project(args.name)
        print(f"Project created: {path}")

    elif args.command == "list-projects":
        projects = manager.list_projects()
        if not projects:
            print("No projects found.")
        else:
            for p in projects:
                print(f"  {p['name']} ({p['slug']}): {p['path']}")

    elif args.command == "delete-project":
        if manager.delete_project(args.name):
            print(f"Deleted project '{args.name}'")
        else:
            print(f"Project '{args.name}' not found.")
            sys.exit(1)

    elif args.command == "ingest":
        from pathlib import Path

        path = Path(args.path).expanduser().resolve()
        pipeline = IngestPipeline(config)

        if path.is_file():
            count = pipeline.ingest_file(args.project, path)
        elif path.is_dir():
            count = pipeline.ingest_directory(args.project, path, recursive=args.recursive)
        else:
            print(f"Path not found: {path}")
            sys.exit(1)

        print(f"Ingested {count} chunks into project '{args.project}'")

    elif args.command == "list-docs":
        project_path = manager.get_project_path(args.project)
        if not project_path.exists():
            print(f"Project '{args.project}' not found.")
            sys.exit(1)
        store = ProjectStore(project_path, config.retrieval)
        docs = store.list_documents()
        if not docs:
            print("No documents ingested.")
        else:
            for title in docs:
                print(f"  {title}")
            print(f"\nTotal chunks: {store.chunk_count()}")

    elif args.command == "delete-doc":
        project_path = manager.get_project_path(args.project)
        if not project_path.exists():
            print(f"Project '{args.project}' not found.")
            sys.exit(1)
        store = ProjectStore(project_path, config.retrieval)
        count = store.delete_document(args.title)
        if count > 0:
            print(f"Deleted {count} chunks for '{args.title}'")
        else:
            print(f"Document '{args.title}' not found.")

    elif args.command == "search":
        project_path = manager.get_project_path(args.project)
        if not project_path.exists():
            print(f"Project '{args.project}' not found.")
            sys.exit(1)
        retriever = Retriever(project_path, config)
        results = retriever.retrieve(args.query, top_k=args.top_k)
        if not results:
            print("No results found.")
        else:
            for i, r in enumerate(results, 1):
                print(f"\n--- Result {i} (score: {r.score:.3f}) ---")
                print(f"Doc: {r.doc_title}")
                if r.section_heading:
                    print(f"Section: {r.section_heading}")
                if r.page_number:
                    print(f"Page: {r.page_number}")
                print(f"Text: {r.text[:200]}...")
