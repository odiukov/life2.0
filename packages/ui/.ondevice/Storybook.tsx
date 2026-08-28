import { getStorybookUI } from '@storybook/react-native';
import './loadStories';

const StorybookUIRoot = getStorybookUI({ enableWebsockets: false });
export default StorybookUIRoot;
