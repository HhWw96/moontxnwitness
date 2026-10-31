"""Validate actual shared-SDK consumer bindings; never creates acceptance data."""
SYMBOLS={
 'diagnose_configured_session_v4_json','verify_configured_session_diagnostic_v4_json',
 'configured_session_options_v4_json','configured_session_bundle_v4_json',
 'verify_source_installation_v4_json','verify_source_installation_report_v4_json',
 'verify_source_fetch_mapping_v4_json','verify_source_fetch_mapping_report_v4_json',
 'normalize_sql_config_v1_json','normalize_configured_sql_v1_json','verify_configured_sql_v1_json',
 'compare_c_text_v1','verify_configured_fetch_v1_json',
}

def validate_shared039_receipt(value,manifest,sdk_sha):
    assert value['format']=='shared-core-runtime-conformance/v1'
    assert value['passed'] is True and type(value['checks']) is int and value['checks']==11
    assert type(value['failed']) is int and value['failed']==0
    assert len(value['results'])==11 and all(row['passed'] is True for row in value['results'])
    assert len({row['name'] for row in value['results']})==11
    assert value['version']==manifest['version']
    assert value['defaultSDKStaticModules']==41
    assert value['defaultSDKCompiledCores']==['core.mjs','capture-core.mjs']
    expected={'core.mjs':manifest['coreSha256'],'capture-core.mjs':manifest['captureCoreSha256'],**manifest['configuredCoreSha256']}
    assert len(expected)==6 and value['roleHashes']==expected
    assert value['sdkSha256']==sdk_sha and value['runtimeBeforeAfterUnchanged'] is True
    assert set(value['primitiveCalls'])==SYMBOLS
    assert all(type(count) is int and count>0 for count in value['primitiveCalls'].values())
    for name in ('actualDatabaseExecution','formalPerformanceMeasurement','sourceFactsProduced','writerWindowVerified'):
        assert value[name] is False
