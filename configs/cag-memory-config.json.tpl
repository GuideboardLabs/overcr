{
  "cag_memory": {
    "enabled": true,
    "source": "{{CAG_MEMORY_PATH}}",
    "integration_mode": "route-based",
    "routes": {
      "{{ROUTE_ID}}": {
        "cag_path": "{{CAG_MEMORY_PATH}}",
        "validated_memories": [],
        "auto_sync": true,
        "sync_frequency_seconds": 86400
      }
    },
    "schema": {
      "memory_id": "string",
      "route_id": "string",
      "timestamp": "iso8601",
      "validated": "boolean",
      "validated_at": "iso8601|null",
      "content": "json",
      "tags": "array",
      "metadata": "json"
    }
  }
}