"""DeepLabeling's core: label files, datasets, queues and app state.

Nothing here imports Qt (tests/core/test_core_imports_no_qt.py checks it), so the
core runs headless and the dataset-analysis scripts can import it.
"""
