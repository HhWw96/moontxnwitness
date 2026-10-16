"""Keep the source, package and compiled-core version inputs in step."""
import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
version = sys.argv[1] if len(sys.argv) == 2 else ""
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
    raise SystemExit("Usage: python scripts/bump_version.py x.y.z")
package = json.loads((root / "package.json").read_text(encoding="utf-8"))
package["version"] = version
(root / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
module = (root / "moon.mod").read_text(encoding="utf-8")
(root / "moon.mod").write_text(re.sub(r'^version = "[^"]+"', 'version = "' + version + '"', module, flags=re.M), encoding="utf-8")
types = (root / "src/types.mbt").read_text(encoding="utf-8")
(root / "src/types.mbt").write_text(re.sub(r'(pub fn version\(\) -> String \{\s*)"[^"]+"', lambda m: m[1] + '"' + version + '"', types), encoding="utf-8")
readme = (root / 'README.md').read_text(encoding='utf-8')
readme = re.sub(r'^# MoonTxnWitness v[0-9.]+', '# MoonTxnWitness v' + version, readme, flags=re.M)
readme = re.sub(r'moon add HhWw96/moontxnwitness@[0-9.]+', 'moon add HhWw96/moontxnwitness@' + version, readme)
readme = re.sub(r'\[v[0-9.]+ 下载\]', '[v' + version + ' 下载]', readme)
readme = re.sub(r'(https://github.com/HhWw96/moontxnwitness/releases/tag/v)[0-9.]+', lambda m: m[1] + version, readme)
(root / 'README.md').write_text(readme, encoding='utf-8')
print("Version inputs updated to " + version)
