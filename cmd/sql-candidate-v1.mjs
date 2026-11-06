// Standalone entry remains bound to its original independent compiled slot.
import * as core from './sql-projection-core.mjs';
import {createSQLCandidateV1} from './sql-candidate-host-v1.mjs';
export {SQL_CANDIDATE_V1_LIMITS} from './sql-candidate-host-v1.mjs';
export const {normalizeSQLConfigV1,normalizeSQLCandidateV1,verifySQLCandidateV1,compareConfiguredCTextV1}=createSQLCandidateV1(core);
