type UnauthorizedListener = () => void;

const listeners = new Set<UnauthorizedListener>();

export function subscribeUnauthorized(listener: UnauthorizedListener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function notifyUnauthorized() {
  for (const listener of listeners) listener();
}
