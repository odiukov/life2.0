export const parse = jest.fn().mockReturnValue({ queryParams: {} });
export const addEventListener = jest.fn().mockReturnValue({ remove: jest.fn() });
export const createURL = jest.fn().mockReturnValue('');
export const openURL = jest.fn().mockResolvedValue(undefined);
