// The default SDK reuses its existing compiled core instance.
import * as core from './core.mjs';
import {createConfiguredWindowV4} from './configured-window-v2-host.mjs';
export const {analyzeConfiguredWindowV4, verifyConfiguredWindowV4,
  analyzeConfiguredWindowTextV4, verifyConfiguredWindowTextV4} = createConfiguredWindowV4(core);
export {CONFIGURED_WINDOW_V4_LIMITS} from './configured-window-v2-host.mjs';
