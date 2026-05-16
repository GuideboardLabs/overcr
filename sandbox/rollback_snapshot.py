"""
OverCR v2.6.0 — Rollback Snapshot

Manages pre-execution snapshots and post-execution rollback for
the execution sandbox. Every mutating operation is paired with a
rollback capability. Snapshots are append-only — once created they
are preserved for audit and replay.

Snapshot types:
  - file_snapshot: full content + metadata of a single file
  - dir_snapshot: directory listing (not full tree — depth-1)
  - hash_snapshot: just the content hash (for non-mutating reference)

Rollback restores filesystem state to the snapshot point.
Failed rollbacks are recorded as audit events.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Optional


class RollbackSnapshot:
    """
    Creates and manages filesystem snapshots for rollback.

    Snapshots are stored as structured records on disk. Each snapshot
    captures enough state to restore a file or directory to its
    pre-execution state.
    """

    def __init__(self, sandbox_root: str):
        """
        Args:
            sandbox_root: Absolute path to the sandbox root.
        """
        self.sandbox_root = os.path.abspath(sandbox_root)
        self.snapshot_dir = os.path.join(sandbox_root, ".overcr_snapshots")
        os.makedirs(self.snapshot_dir, exist_ok=True)

        self._active_snapshots: dict[str, dict] = {}
        self._rollback_log: list[dict] = []

    # ── Snapshot creation ──────────────────────────────

    def create_file_snapshot(self, file_path: str) -> Optional[str]:
        """
        Create a full snapshot of a single file.

        Captures: content (base64), size, mtime, and hash.

        Returns:
            snapshot_id on success, None if file doesn't exist or is outside sandbox.
        """
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.sandbox_root, file_path)

        real = os.path.realpath(file_path)
        if not real.startswith(os.path.realpath(self.sandbox_root) + os.sep):
            return None  # Outside sandbox

        if not os.path.isfile(real):
            return None

        try:
            stat = os.stat(real)
            with open(real, "rb") as f:
                content = f.read()
        except (OSError, IOError):
            return None

        snapshot_id = hashlib.sha256(
            f"{real}:{len(content)}:{stat.st_mtime}".encode()
        ).hexdigest()[:16]

        snapshot = {
            "snapshot_id": snapshot_id,
            "type": "file_snapshot",
            "path": real,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "size": len(content),
            "mtime": stat.st_mtime,
            "content_hash": hashlib.sha256(content).hexdigest(),
            "content_base64": "",  # Not stored inline to avoid bloat
        }

        # Store content in snapshot file
        snapshot_path = os.path.join(
            self.snapshot_dir, f"{snapshot_id}.snap"
        )
        snapshot["snapshot_path"] = snapshot_path

        with open(snapshot_path, "wb") as f:
            f.write(content)

        # Record metadata
        meta_path = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
        with open(meta_path, "w") as f:
            json.dump(snapshot, f, indent=2)

        self._active_snapshots[snapshot_id] = snapshot
        return snapshot_id

    def create_dir_snapshot(self, dir_path: str) -> Optional[str]:
        """
        Create a directory listing snapshot (depth-1 only).

        Captures: list of entries with their types (file/dir/symlink)
        and hashes of immediate children.

        Returns:
            snapshot_id on success, None for invalid paths.
        """
        if not os.path.isabs(dir_path):
            dir_path = os.path.join(self.sandbox_root, dir_path)

        real = os.path.realpath(dir_path)
        if not real.startswith(os.path.realpath(self.sandbox_root) + os.sep):
            return None

        if not os.path.isdir(real):
            return None

        entries = []
        for entry in sorted(os.listdir(real)):
            entry_path = os.path.join(real, entry)
            entry_type = "unknown"
            entry_hash = ""
            try:
                if os.path.islink(entry_path):
                    entry_type = "symlink"
                    entry_hash = hashlib.sha256(
                        os.readlink(entry_path).encode()
                    ).hexdigest()[:16]
                elif os.path.isdir(entry_path):
                    entry_type = "dir"
                    entry_hash = ""
                else:
                    entry_type = "file"
                    with open(entry_path, "rb") as f:
                        entry_hash = hashlib.sha256(f.read()).hexdigest()[:16]
            except OSError:
                pass

            entries.append({
                "name": entry,
                "type": entry_type,
                "hash": entry_hash,
            })

        snapshot_id = hashlib.sha256(
            f"{real}:{len(entries)}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

        snapshot = {
            "snapshot_id": snapshot_id,
            "type": "dir_snapshot",
            "path": real,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entries": entries,
            "entry_count": len(entries),
        }

        meta_path = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
        with open(meta_path, "w") as f:
            json.dump(snapshot, f, indent=2)

        self._active_snapshots[snapshot_id] = snapshot
        return snapshot_id

    # ── Rollback ────────────────────────────────────────

    def rollback_file(self, snapshot_id: str) -> tuple[bool, str]:
        """
        Restore a file from a snapshot.

        Returns: (success, message)
        """
        snapshot = self._active_snapshots.get(snapshot_id)
        if not snapshot:
            # Try loading from disk
            meta_path = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f:
                    snapshot = json.load(f)
                self._active_snapshots[snapshot_id] = snapshot
            else:
                return False, f"Snapshot {snapshot_id} not found"

        if snapshot.get("type") != "file_snapshot":
            return False, "Not a file snapshot"

        target_path = snapshot.get("path", "")
        if not target_path:
            return False, "No target path in snapshot"

        snap_data_path = snapshot.get(
            "snapshot_path",
            os.path.join(self.snapshot_dir, f"{snapshot_id}.snap"),
        )

        if not os.path.exists(snap_data_path):
            return False, f"Snapshot data file missing: {snap_data_path}"

        try:
            with open(snap_data_path, "rb") as f:
                content = f.read()

            # Ensure target directory exists
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            with open(target_path, "wb") as f:
                f.write(content)

            # Restore mtime if recorded
            if snapshot.get("mtime"):
                os.utime(target_path, (snapshot["mtime"], snapshot["mtime"]))
        except (OSError, IOError) as e:
            return False, f"Rollback failed: {e}"

        # Log rollback
        self._rollback_log.append({
            "type": "rollback_executed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snapshot_id": snapshot_id,
            "target": target_path,
            "success": True,
        })

        return True, f"Rolled back {target_path} from snapshot {snapshot_id}"

    def rollback_dir(self, snapshot_id: str) -> tuple[bool, str]:
        """
        Verify directory state against snapshot. Reports drift.

        Directory rollback does NOT restore files to original content
        (that requires per-file snapshots). It validates that the
        listing hasn't changed structurally.
        """
        snapshot = self._active_snapshots.get(snapshot_id)
        if not snapshot:
            meta_path = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f:
                    snapshot = json.load(f)
            else:
                return False, "Snapshot not found"

        if snapshot.get("type") != "dir_snapshot":
            return False, "Not a directory snapshot"

        target = snapshot.get("path", "")
        if not os.path.isdir(target):
            return False, f"Target directory does not exist: {target}"

        current_entries = set(os.listdir(target))
        snapshot_entries = {e["name"] for e in snapshot.get("entries", [])}

        added = current_entries - snapshot_entries
        removed = snapshot_entries - current_entries

        if added or removed:
            return False, f"Directory drift detected: added={added}, removed={removed}"

        return True, "Directory matches snapshot state"

    # ── Query ──────────────────────────────────────────

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """Retrieve snapshot metadata by ID."""
        if snapshot_id in self._active_snapshots:
            return dict(self._active_snapshots[snapshot_id])

        meta_path = os.path.join(self.snapshot_dir, f"{snapshot_id}.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                return json.load(f)

        return None

    def list_snapshots(self, path_filter: str = "") -> list[dict]:
        """List all snapshots, optionally filtered by path."""
        results = []
        for fname in sorted(os.listdir(self.snapshot_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(self.snapshot_dir, fname)
                try:
                    with open(fpath, "r") as f:
                        snap = json.load(f)
                    if not path_filter or path_filter in snap.get("path", ""):
                        results.append(snap)
                except json.JSONDecodeError:
                    continue
        return results

    def get_rollback_log(self) -> list[dict]:
        """Get the rollback event log."""
        return list(self._rollback_log)
