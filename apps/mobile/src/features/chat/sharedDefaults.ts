import { NativeModules } from 'react-native';

const { SharedDefaults } = NativeModules as {
  SharedDefaults: {
    getPendingFileName(): Promise<string | null>;
    getPendingFileURL(): Promise<string | null>;
    clearPendingFileName(): Promise<void>;
  };
};

export { SharedDefaults };
