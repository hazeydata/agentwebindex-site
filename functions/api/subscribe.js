// POST /api/subscribe (AWI-SIGNUP-FORM-001). Logic in signup/core.js.
import { handleSubscribe } from '../../signup/core.js';
export const onRequest = (context) => handleSubscribe(context.request, context.env);
