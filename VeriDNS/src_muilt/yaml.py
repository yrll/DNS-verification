def safe_load(stream):
    text = stream.read() if hasattr(stream, "read") else str(stream)
    root = {}
    stack = [(-1, root)]
    lines = text.splitlines()

    for index, raw_line in enumerate(lines):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if not isinstance(parent, list):
                raise ValueError("List item without list parent")
            if ":" in item:
                key, value = item.split(":", 1)
                obj = {key.strip(): _parse_scalar(value.strip())}
                parent.append(obj)
                stack.append((indent, obj))
            else:
                parent.append(_parse_scalar(item))
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            parent[key] = _parse_scalar(value)
            continue

        child = [] if _next_content_is_list(lines, index, indent) else {}
        parent[key] = child
        stack.append((indent, child))

    return root


def _parse_scalar(value):
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _next_content_is_list(lines, index, current_indent):
    for line in lines[index + 1:]:
        content = line.split("#", 1)[0].rstrip()
        if not content.strip():
            continue
        indent = len(content) - len(content.lstrip(" "))
        return indent > current_indent and content.strip().startswith("- ")
    return False
