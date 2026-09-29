"""Resolve the single file chooser's copy/direct mode without overwriting existing copies."""
from pathlib import Path
from history_excel import WorkbookSync, import_source


def select_workbook(source: Path, use_copy: bool, previous: dict) -> Path:
    source = source.resolve()
    sync = WorkbookSync(source)
    sync.close()
    if not use_copy:
        return source
    output = source.with_name(source.stem + "_已完成.xlsx")
    # Reuse only an explicitly established source/copy pair, not an unrelated old file.
    if (previous.get("source") == str(source)
            and previous.get("copy_workbook", previous.get("workbook")) == str(output)
            and output.is_file()):
        sync = WorkbookSync(output)
        sync.close()
        return output
    return import_source(source)
