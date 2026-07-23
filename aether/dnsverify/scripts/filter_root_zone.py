from pathlib import Path

SUPPORTED_TYPES = {"A", "AAAA", "CNAME", "DNAME", "MX", "NS", "PTR", "SOA", "TXT"}
CLASSES = {"IN", "CH", "HS"}


def record_type(tokens):
    for token in tokens:
        upper = token.upper()
        if upper in CLASSES:
            continue
        if upper.isdigit():
            continue
        return upper
    return ""


def convert_owner(owner):
    if owner == ".":
        return "@"
    if owner.endswith("."):
        return f"{owner[:-1]}.root."
    return f"{owner}.root."


def convert_rdata(parts, rtype_index):
    rtype = parts[rtype_index].upper()
    domain_fields = {
        "NS": [rtype_index + 1],
        "CNAME": [rtype_index + 1],
        "DNAME": [rtype_index + 1],
        "PTR": [rtype_index + 1],
        "SOA": [rtype_index + 1, rtype_index + 2],
        "MX": [rtype_index + 2],
    }
    for idx in domain_fields.get(rtype, []):
        if idx < len(parts) and parts[idx].endswith("."):
            parts[idx] = convert_owner(parts[idx])


def main():
    base = Path("datasets/root-zone")
    raw_path = base / "root.zone.raw"
    out_path = base / "root.zone"

    kept = 0
    skipped = 0
    with raw_path.open("r", encoding="utf-8", errors="replace") as src, out_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as dst:
        dst.write("$ORIGIN root.\n")
        dst.write("$TTL 86400\n")
        for line in src:
            stripped = line.strip()
            if not stripped or stripped.startswith(";") or stripped.startswith("$"):
                continue

            parts = stripped.split()
            if len(parts) < 4:
                skipped += 1
                continue

            rtype = record_type(parts[1:])
            if rtype not in SUPPORTED_TYPES:
                skipped += 1
                continue

            rtype_index = next(i for i, part in enumerate(parts) if part.upper() == rtype)
            parts[0] = convert_owner(parts[0])
            convert_rdata(parts, rtype_index)
            dst.write(" ".join(parts) + "\n")
            kept += 1

    print(f"wrote {out_path}")
    print(f"kept={kept} skipped={skipped}")


if __name__ == "__main__":
    main()
