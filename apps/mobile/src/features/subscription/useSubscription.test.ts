import { renderHook } from '@testing-library/react-native';
import { useSubscription } from './useSubscription';

describe('useSubscription', () => {
  it('returns loading: false immediately', () => {
    const { result } = renderHook(() => useSubscription());
    expect(result.current.loading).toBe(false);
  });

  it('balance.used is less than balance.total', () => {
    const { result } = renderHook(() => useSubscription());
    expect(result.current.balance.used).toBeLessThan(result.current.balance.total);
  });

  it('balance has renewsOn and weekUsed fields', () => {
    const { result } = renderHook(() => useSubscription());
    expect(typeof result.current.balance.renewsOn).toBe('string');
    expect(typeof result.current.balance.weekUsed).toBe('number');
  });

  it('plan has active boolean and renewsOn string', () => {
    const { result } = renderHook(() => useSubscription());
    expect(typeof result.current.plan.active).toBe('boolean');
    expect(typeof result.current.plan.renewsOn).toBe('string');
  });

  it('exposes purchase, startPlan, managePlan, restore as functions', () => {
    const { result } = renderHook(() => useSubscription());
    expect(typeof result.current.purchase).toBe('function');
    expect(typeof result.current.startPlan).toBe('function');
    expect(typeof result.current.managePlan).toBe('function');
    expect(typeof result.current.restore).toBe('function');
  });

  it('purchase resolves without throwing', async () => {
    const { result } = renderHook(() => useSubscription());
    await expect(result.current.purchase('flow')).resolves.toBeUndefined();
  });

  it('startPlan resolves without throwing', async () => {
    const { result } = renderHook(() => useSubscription());
    await expect(result.current.startPlan()).resolves.toBeUndefined();
  });

  it('restore resolves without throwing', async () => {
    const { result } = renderHook(() => useSubscription());
    await expect(result.current.restore()).resolves.toBeUndefined();
  });

  it('managePlan does not throw when called', () => {
    const { result } = renderHook(() => useSubscription());
    expect(() => result.current.managePlan()).not.toThrow();
  });
});
