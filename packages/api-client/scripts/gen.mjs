import { execSync } from 'node:child_process';

execSync(
  'pnpm exec openapi-typescript schema/openapi.yaml -o src/generated.ts',
  { stdio: 'inherit' },
);
