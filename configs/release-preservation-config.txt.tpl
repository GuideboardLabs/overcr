# Release Artifacts Preservation Configuration
# DO NOT MODIFY - defines separation of live state from archival releases

ARCHIVE_ROOT={{ARCHIVE_ROOT}}
LIVE_ROOT={{OVERCR_ROOT}}

# Symlink Policy: DO NOT symlink release artifacts into live workspace
# Release artifacts remain in archive root and are referenced read-only

SYMLINK_POLICY=disabled
READONLY_ACCESS=enabled

# Release Artifacts List
# Populate with actual artifact filenames after each release
RELEASE_ARTIFACTS=()

# Integrity Verification
INTEGRITY_CHECK=enabled
CHECKSUMS=( sha256 )

# Boot Manifest
BOOT_MANIFEST={{OVERCR_ROOT}}/HQ_BOOT_MANIFEST.md
STATE_FILE={{OVERCR_ROOT}}/overcr_state.json