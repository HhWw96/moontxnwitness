// Standalone entry remains bound to its original independent compiled slot.
import * as core from './sql-fetch-core.mjs';
import {createSQLFetchV1} from './sql-fetch-host-v1.mjs';
export {SQL_FETCH_V1_LIMITS} from './sql-fetch-host-v1.mjs';
export const {verifyConfiguredFetchV1}=createSQLFetchV1(core);
