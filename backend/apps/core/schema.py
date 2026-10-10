"""OpenAPI post-processing.

drf-spectacular marks writable fields with a model default (e.g. `timezone`, `num_loops`)
as optional everywhere. That's right for request bodies, but a response always contains
every declared field — so we mark all response properties required. The generated
TypeScript types then say `timezone: string`, not `timezone?: string`, and the frontend
doesn't need defensive fallbacks for values the API always sends.
"""

from typing import Any


def require_response_fields(result: dict[str, Any], **_: Any) -> dict[str, Any]:
    for name, component in result.get("components", {}).get("schemas", {}).items():
        if name.endswith("Request") or "properties" not in component:
            continue
        component["required"] = sorted(component["properties"])
    return result
