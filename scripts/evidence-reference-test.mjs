import assert from 'node:assert/strict';
import path from 'node:path';
import {relativeEvidencePath} from './evidence-reference.mjs';

let checks = 0;
for (const [paths, root, inside, outside] of [
  [path.posix, '/home/runner/work/repo/repo', '/home/runner/work/repo/repo/artifacts/run/receipt.json', '/home/runner/work/repo/repo-other/receipt.json'],
  [path.win32, 'D:\\work\\repo', 'D:\\work\\repo\\artifacts\\run\\receipt.json', 'D:\\work\\repo-other\\receipt.json'],
]) {
  assert.equal(relativeEvidencePath(root, inside, paths), 'artifacts/run/receipt.json'); checks++;
  for (const rejected of [outside, root, '', 'artifacts/receipt.json', undefined]) {
    assert.throws(() => relativeEvidencePath(root, rejected, paths)); checks++;
  }
}
assert.throws(() => relativeEvidencePath('D:\\work\\repo', 'E:\\receipt.json', path.win32)); checks++;
console.log(JSON.stringify({passed: true, checks}));
