// Default SDK shares the main MoonBit instance. Standalone entries remain separate.
import * as core from './core.mjs';
import {createConfiguredSessionV4} from './configured-session-v4.mjs';
import {createSourceComponentsV4} from './source-components-v4.mjs';
import {createSQLCandidateV1} from './sql-candidate-host-v1.mjs';
import {createSQLFetchV1} from './sql-fetch-host-v1.mjs';
export const {diagnoseConfiguredSessionTextV4,diagnoseConfiguredSessionV4,verifyConfiguredSessionV4,
 normalizeConfiguredSessionOptionsV4,makeConfiguredSessionCapsuleV4,replayConfiguredSessionCapsuleV4}=createConfiguredSessionV4(core);
export const {verifySourceInstallationV4,verifySourceInstallationReportV4,mapInitialSourceFetchV4,
 verifyInitialSourceFetchReportV4}=createSourceComponentsV4(core);
export const {normalizeSQLConfigV1,normalizeSQLCandidateV1,verifySQLCandidateV1,compareConfiguredCTextV1}=createSQLCandidateV1(core);
export const {verifyConfiguredFetchV1}=createSQLFetchV1(core);
export {CONFIGURED_SESSION_LIMITS} from './configured-session-v4.mjs';
