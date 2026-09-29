import os
import tempfile

# Tests run against an isolated database / index directory (never the developer's var/).
os.environ["VAR_DIR"] = tempfile.mkdtemp(prefix="yokoten-test-")
