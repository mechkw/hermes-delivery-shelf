"""Native Hermes registrations. No scanning, hooks, network, or model calls."""
import importlib.util
import json
from pathlib import Path
import sys
import threading

_lock = threading.Lock()
_api = None


def _service():
    global _api
    with _lock:
        if _api is None:
            name = __name__ + ".shelf_api"
            spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "dashboard" / "plugin_api.py")
            if spec is None or spec.loader is None:
                raise RuntimeError("Delivery Shelf service is unavailable")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(name, None)
                raise
            _api = module
        return _api


def _run(action, args):
    from pydantic import ValidationError
    from fastapi import HTTPException
    api = _service()
    try:
        store = api.Store(api.bound_home())
        if action == "register":
            result = store.create(api.EntryInput.model_validate(args))
        else:
            # Tool schemas are guidance, not validation: validate every argument.
            allowed = {"q", "tag", "kind", "project", "limit", "offset"}
            if set(args) - allowed:
                raise ValueError("Unknown search field")
            for key, maximum in (("q", 200), ("tag", 40), ("kind", 40), ("project", 100)):
                if key in args and (not isinstance(args[key], str) or len(args[key]) > maximum):
                    raise ValueError("Invalid search field")
            for key, low, high in (("limit", 1, 100), ("offset", 0, 1000000)):
                if key in args and (type(args[key]) is not int or not low <= args[key] <= high):
                    raise ValueError("Invalid pagination")
            result = store.search(**args)
        return json.dumps({"ok": True, "data": result})
    except ValidationError:
        return json.dumps({"ok": False, "error": "Invalid metadata or unsafe file reference"})
    except HTTPException as exc:
        return json.dumps({"ok": False, "error": exc.detail})
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except (OSError, __import__("sqlite3").Error):
        return json.dumps({"ok": False, "error": "Catalog unavailable; check profile storage permissions"})


def register(ctx):
    api = _service()
    ctx.register_tool(
        name="delivery_shelf_register", toolset="delivery_shelf",
        description="Register an explicitly chosen deliverable in this profile's Delivery Shelf.",
        schema={"name": "delivery_shelf_register", "description": "Register ONLY a deliverable the user explicitly wants saved. Metadata is local; optional file uses an operator-approved root alias and relative path. Never scan folders or register secrets.", "parameters": api.EntryInput.model_json_schema()},
        handler=lambda args, **kwargs: _run("register", {**({"session_id": kwargs["session_id"]} if kwargs.get("session_id") else {}), **args}), check_fn=lambda: True,
    )
    ctx.register_tool(
        name="delivery_shelf_search", toolset="delivery_shelf",
        description="Search registered deliverable metadata, without reading files.",
        schema={"name": "delivery_shelf_search", "description": "Search this profile's explicitly registered deliveries by title/description, exact tag, kind or project. Returns metadata only, never scans files.", "parameters": {"type": "object", "additionalProperties": False, "properties": {"q": {"type": "string", "maxLength": 200}, "tag": {"type": "string", "maxLength": 40}, "kind": {"type": "string", "enum": ["document", "image", "report", "code", "other"]}, "project": {"type": "string", "maxLength": 100}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "offset": {"type": "integer", "minimum": 0, "maximum": 1000000}}}},
        handler=lambda args, **kwargs: _run("search", args), check_fn=lambda: True,
    )
    def command(raw_args):
        result = json.loads(_run("search", {"q": raw_args.strip(), "limit": 20}))
        if not result["ok"]:
            return "Delivery Shelf: " + result["error"]
        data = result["data"]
        lines = [f"Delivery Shelf — {data['total']} matching deliveries"]
        lines.extend(f"• {item['title']} [{item['kind']}] — {item['id']}" for item in data["items"])
        lines.append("Open Delivery Shelf in Dashboard or Desktop to add, edit, preview or remove metadata.")
        return "\n".join(lines)
    ctx.register_command("shelf", command, description="Search your Delivery Shelf", args_hint="[search text]", argument_mode="text")
