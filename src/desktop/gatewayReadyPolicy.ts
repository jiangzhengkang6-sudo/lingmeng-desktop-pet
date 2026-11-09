export type GatewayHealthState = 'idle' | 'checking' | 'ready' | 'error'

/**
 * 判断网关状态变化后是否需要补刷业务数据。
 * 仅首次 ready，以及异常恢复时的 error -> ready 会触发；
 * 普通刷新造成的 ready -> checking -> ready 不应重复触发。
 */
export function shouldRefreshGatewayDataOnReady(
  nextState: GatewayHealthState,
  previousState: GatewayHealthState | undefined,
  hasObservedReady: boolean,
): boolean {
  return nextState === 'ready' && (!hasObservedReady || previousState === 'error')
}
