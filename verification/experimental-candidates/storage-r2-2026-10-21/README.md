# Experimental archive reader and original-segment retirement, revision 2

This bundle preserves the frozen candidate index `7a014774…918079` and its
dependencies byte for byte. The runner restores their original relative paths
under a new temporary directory. It does not replace production source or the
default journal API.

The manual **Verify frozen experimental storage** workflow executes 33 new fault
cases and separately reruns 32 earlier cases against this revised implementation,
on Linux and Windows. These are written cases until the workflow produces actual
receipts. A host symlink privilege skip is recorded rather than counted as an
executed pass. Source before/after hashes, crash logs and raw test directories are
preserved in the workflow artifacts.

Reproduce with Python 3.12 and a fresh destination:

```
python -B scripts/experimental_storage_ci.py --work /path/to/new/mtw-storage-r2
```

The prototype covers sealed, source-closed unique-version point-register logs.
It does not establish SQL/ORM window integration, list or relation closure,
physical power-loss durability, complete capture cost, performance gates, or
independent acceptance. The original prototype's 30 passes and two Windows
skips remain evidence for its original source, not this revision.
