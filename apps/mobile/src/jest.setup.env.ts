// Load .env.local for Jest so EXPO_PUBLIC_* vars match the dev environment.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const dotenv = require('dotenv');
const path = require('path');
dotenv.config({ path: path.resolve(__dirname, '../.env.local') });
