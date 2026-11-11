import { describe, expect, it } from 'vitest';
import { GameApiError } from '@/lib/game-client';
import { isUnreachable } from '@/components/game/use-game';

describe('isUnreachable', () => {
  it('treats a dropped connection and a down backend behind the proxy as offline', () => {
    expect(isUnreachable(new GameApiError('BACKEND_UNAVAILABLE', 0, 'x'))).toBe(true);
    expect(isUnreachable(new GameApiError('BACKEND_UNAVAILABLE', 502, 'x'))).toBe(true);
    expect(isUnreachable(new GameApiError('HTTP_ERROR', 503, 'x'))).toBe(true);
    expect(isUnreachable(new GameApiError('HTTP_ERROR', 504, 'x'))).toBe(true);
  });
  it('keeps ordinary API answers as connected', () => {
    expect(isUnreachable(new GameApiError('VALIDATION_ERROR', 422, 'x'))).toBe(false);
    expect(isUnreachable(new GameApiError('STATE_CONFLICT', 409, 'x'))).toBe(false);
    expect(isUnreachable(new GameApiError('UNAUTHENTICATED', 401, 'x'))).toBe(false);
    expect(isUnreachable(new Error('x'))).toBe(false);
  });
});
