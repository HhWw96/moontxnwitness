// The portable entry point is the same workflow exercised by development and CI.
process.argv.push('--record-verification');
await import('../dist/postgres-demo.mjs');
