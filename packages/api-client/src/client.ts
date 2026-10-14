import createClient from 'openapi-fetch';
import type { ClientOptions } from 'openapi-fetch';
import type { paths } from './generated';
import type { paths as GatewayPaths, components as GatewayComponents } from './gateway';

export function createApiClient(opts: ClientOptions) {
  return createClient<paths>(opts);
}

export type { paths };

export function createGatewayClient(opts: ClientOptions) {
  return createClient<GatewayPaths>(opts);
}

export type GatewaySchemas = GatewayComponents['schemas'];
export type { GatewayPaths };
