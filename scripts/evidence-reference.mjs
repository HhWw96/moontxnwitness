import path from 'node:path';

// Public summaries link retained evidence relative to the checkout. The raw
// runner stdout and original receipts remain unchanged in private artifacts.
export function relativeEvidencePath(root, value, paths = path) {
  if (typeof value !== 'string' || !value || !paths.isAbsolute(value)) {
    throw new TypeError('Evidence reference must identify an absolute retained path');
  }
  const relative = paths.relative(root, value);
  if (!relative || paths.isAbsolute(relative) || relative === '..' || relative.startsWith('..' + paths.sep)) {
    throw new RangeError('Evidence reference must remain inside the checkout');
  }
  return relative.split(paths.sep).join('/');
}
