import createClient from 'openapi-fetch';
import type { ClientOptions } from 'openapi-fetch';
import type { paths } from './generated';

export function createApiClient(opts: ClientOptions) {
  return createClient<paths>(opts);
}

export type { paths };
