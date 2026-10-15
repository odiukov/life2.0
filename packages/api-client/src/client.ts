import createClient from 'openapi-fetch';
import type { ClientOptions } from 'openapi-fetch';
import type { paths as GatewayPaths, components as GatewayComponents } from './gateway';

export function createGatewayClient(opts: ClientOptions) {
  return createClient<GatewayPaths>(opts);
}

export type GatewaySchemas = GatewayComponents['schemas'];
export type { GatewayPaths };
