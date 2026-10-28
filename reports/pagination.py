from django.conf import settings


def paginate(result, rows_per_page=None):
    """Split a report's sections into fixed-size pages.

    The same page list drives the on-screen viewer and the PDF, so
    "page 4" means the same thing in both.
    """
    size = rows_per_page or settings.REPORT_ROWS_PER_PAGE
    pages = []
    for section in result.get("sections", []):
        rows = section["rows"]
        chunks = [rows[i : i + size] for i in range(0, len(rows), size)] or [[]]
        for index, chunk in enumerate(chunks):
            last = index == len(chunks) - 1
            pages.append(
                {
                    "title": section["title"],
                    "part": f"{index + 1} of {len(chunks)}" if len(chunks) > 1 else "",
                    "columns": section["columns"],
                    "rows": chunk,
                    "totals": section.get("totals") if last else None,
                    "note": section.get("note", ""),
                }
            )
    return pages
