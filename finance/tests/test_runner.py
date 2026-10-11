"""The standalone runner must isolate artifacts and fail closed on broken tests."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from finance.tests.harness import check, run

RUNNER = Path(__file__).resolve().parents[2] / "bin/test.sh"


def invoke(source=None):
    with tempfile.TemporaryDirectory() as work:
        root = Path(work)
        (root / "bin").mkdir()
        (root / "finance").mkdir()
        (root / "skills").mkdir()
        shutil.copyfile(RUNNER, root / "bin/test.sh")
        if source is not None:
            (root / "finance/test_probe.py").write_text(source)
        external = root / "personal-artifacts"
        result = subprocess.run(["bash", "bin/test.sh"], cwd=root,
                                env={**os.environ, "EVERYTHING_FINANCE_ARTIFACTS": str(external)},
                                capture_output=True, text=True)
        return result, external.exists()


def test_runner_isolates_inherited_artifacts():
    result, touched = invoke("import os\nfrom pathlib import Path\np = Path(os.environ['EVERYTHING_FINANCE_ARTIFACTS'])\np.mkdir(exist_ok=True)\n(p / 'test-output').write_text('fixture')\nprint('1 passed, 0 failed')\n")
    check("valid test passes", result.returncode == 0, result.stdout)
    check("test never writes into the inherited personal artifact root", not touched)


def test_runner_requires_assertion_summary():
    for source in ("print('finished')\n", "print('0 passed, 0 failed')\n", None):
        result, _ = invoke(source)
        check("missing tests or missing assertions fail the gate", result.returncode != 0,
              result.stdout)


if __name__ == "__main__":
    run(globals())
