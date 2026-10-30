import { describe, expect, it } from 'vitest';
import { passwordLengthHint, validPasswordLength } from '@/lib/password';
import { fitMapViewport } from '@/lib/viewport-layout';
import { requestKey } from '@/lib/game-client';

describe('password length', () => {
  it('counts code points so emoji passwords match the backend rule', () => {
    expect(validPasswordLength('😀'.repeat(12))).toBe(true);
    expect(validPasswordLength('a'.repeat(11))).toBe(false);
    expect(validPasswordLength('a'.repeat(129))).toBe(false);
    expect(passwordLengthHint('abc')).toContain('還差 9 字');
    expect(passwordLengthHint('a'.repeat(12))).toBe('密碼長度符合規則。');
  });
});

describe('fitMapViewport', () => {
  it('never exceeds the window and keeps the artwork ratio within bounds', () => {
    for (const [w, h] of [
      [320, 640],
      [390, 844],
      [1440, 900],
      [2560, 600],
    ]) {
      const v = fitMapViewport(w, h);
      expect(v.width).toBeLessThanOrEqual(w);
      expect(v.height).toBeLessThanOrEqual(h);
      const ratio = (v.width - 20) / (v.height - 20);
      expect(ratio).toBeGreaterThanOrEqual(1672 / 941 - 0.01);
      expect(ratio).toBeLessThanOrEqual(2120 / 742 + 0.01);
    }
  });
});

describe('requestKey', () => {
  it('is unique per call', () => {
    const keys = new Set(Array.from({ length: 50 }, requestKey));
    expect(keys.size).toBe(50);
  });
});
