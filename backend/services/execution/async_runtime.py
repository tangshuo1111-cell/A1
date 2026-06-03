"""Async control plane runtime helpers: unified worker startup."""

from __future__ import annotations


def ensure_async_workers_started() -> None:
    """Start unified task-plane workers."""
    from workers.entry.task_plane_worker import ensure_task_plane_workers_started

    ensure_task_plane_workers_started()
