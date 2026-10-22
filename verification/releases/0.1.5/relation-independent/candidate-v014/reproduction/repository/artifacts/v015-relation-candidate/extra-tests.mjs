  check('six-relation-exports-and-all-previous-sdk-entries-remain-present', () => {
    const added = [
      'analyzeRelationV3', 'makeRelationCapsuleV3', 'normalizeRelationCaptureV3',
      'reduceRelationV3', 'replayRelationCapsuleV3', 'verifyRelationV3',
    ];
    for (const name of [...added, 'analyzeV3', 'normalizeCaptureV3', 'reduceV3', 'verifyV3',
      'makeCapsuleV3', 'replayCapsuleV3', 'analyzeListV3', 'normalizeListCaptureV3',
      'reduceListV3', 'verifyListV3', 'makeListCapsuleV3', 'replayListCapsuleV3']) {
      assert.equal(typeof sdk[name], 'function');
    }
    receipt.priorSdkSnapshotAvailable = baseline !== sdk;
    if (baseline !== sdk) assert.deepEqual(Object.keys(sdk).filter(name => !(name in baseline)).sort(), added.sort());
  });
  check('all-released-list-entry-behavior-remains-identical', () => {
    const cases = load('fixtures/list-v3/manual.json');
    for (const row of cases) {
      const trace = JSON.parse(row.traceText);
      if (trace.traceSchema !== 3 || trace.dataModel !== 'append-list-v1') {
        assert.throws(() => sdk.analyzeListV3(row.traceText, row.options), TypeError);
        assert.throws(() => baseline.analyzeListV3(row.traceText, row.options), TypeError);
        continue;
      }
      const normalized = sdk.normalizeListCaptureV3(row.traceText);
      assert.deepEqual(normalized, baseline.normalizeListCaptureV3(row.traceText));
      assert.equal(normalized.status, row.expected.normalization);
      const report = sdk.analyzeListV3(row.traceText, row.options);
      assert.deepEqual(report, baseline.analyzeListV3(row.traceText, row.options));
      assert.equal(report.status, row.expected.analysis);
      assert.deepEqual(sdk.verifyListV3(row.traceText, report), baseline.verifyListV3(row.traceText, report));
      let oldCapsule;
      try {oldCapsule = baseline.makeListCapsuleV3(row.traceText, report);}
      catch (error) {
        assert.throws(() => sdk.makeListCapsuleV3(row.traceText, report),
          actual => actual.constructor === error.constructor && actual.message === error.message);
        (receipt.preservedListCapsuleRejections ??= []).push(row.id);
        continue;
      }
      const capsule = sdk.makeListCapsuleV3(row.traceText, report);
      assert.equal(capsule, oldCapsule);
      assert.deepEqual(sdk.replayListCapsuleV3(capsule), baseline.replayListCapsuleV3(capsule));
    }
    const source = load('fixtures/list-v3/reduction-source-closure.json');
    assert.deepEqual(sdk.reduceListV3(source), baseline.reduceListV3(source));
    receipt.preservedListManualCases = cases.length;
  });
  check('declared-relation-without-schema-remains-invalid-instead-of-being-filled-in', () => {
    const input = JSON.parse(traceText); delete input.relationSchema;
    const report = sdk.analyzeRelationV3(input);
    assert.equal(report.status, 'invalid');
    assert.equal(report.coverage.complete, false);
    assert.deepEqual(report, baseline.analyzeV3(input));
    assert.equal(sdk.replayRelationCapsuleV3(sdk.makeRelationCapsuleV3(input, report)).status, 'invalid');
  });
