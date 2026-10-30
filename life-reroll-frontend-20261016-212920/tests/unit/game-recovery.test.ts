import { describe, expect, it } from 'vitest';
import { GameClient } from '@/lib/game-client';
import { GameRecovery } from '@/lib/game-recovery';

function memory() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    dump: () => [...m.values()].join('\n'),
  };
}
const client = new GameClient(async () => new Response('{}'), 'https://api.example');

describe('GameRecovery', () => {
  it('keeps the original key for a gameplay write until acknowledged', () => {
    const storage = memory();
    const recovery = new GameRecovery(storage, 'https://api.example');
    const plan = client.plan('D01', { run_id: 'run-1' }, { expected_version: 3 });
    recovery.begin('user', 'D01', plan);
    expect(recovery.read('user')?.request?.key).toBe(plan.key);
    recovery.acknowledge('user', 'job-1');
    expect(recovery.read('user')).toEqual({ request: undefined, jobId: 'job-1' });
    recovery.acknowledge('user');
    expect(recovery.read('user')).toBeNull();
  });

  it('never stores account requests that carry secrets', () => {
    const storage = memory();
    const recovery = new GameRecovery(storage);
    recovery.begin('user', 'A02', client.plan('A02', {}, { password: 'must-not-save' }));
    expect(storage.dump()).not.toContain('must-not-save');
    expect(recovery.read('user')).toBeNull();
  });

  it('isolates API servers and users, and rejects tampered entries', () => {
    const storage = memory();
    new GameRecovery(storage, 'one').begin('user', 'D01', client.plan('D01', { run_id: 'r' }, {}));
    expect(new GameRecovery(storage, 'two').read('user')).toBeNull();
    expect(new GameRecovery(storage, 'one').read('other')).toBeNull();
    storage.setItem(
      'life-reroll:recovery:v1:one:user',
      JSON.stringify({
        version: 1,
        userId: 'user',
        request: { method: 'POST', path: '/api/v1/auth/login', key: 'k' },
      }),
    );
    expect(new GameRecovery(storage, 'one').read('user')).toBeNull();
  });
});

describe('GameClient', () => {
  it('fills and encodes path parameters from the registry', () => {
    const plan = client.plan('D01', { run_id: 'a/b' }, {});
    expect(plan).toMatchObject({ method: 'POST', path: '/api/v1/runs/a%2Fb/advances' });
    expect(() => client.plan('D01', {}, {})).toThrow('Missing run_id');
    expect(() => client.plan('ZZ9')).toThrow('Unknown operation');
  });

  it('only builds URLs for API paths on the configured origin', () => {
    expect(client.url('/api/v1/bootstrap')).toBe('https://api.example/api/v1/bootstrap');
    for (const bad of ['/admin', '/api/v1/../x', 'https://evil.example/api/v1/x', '/api/v1/https://evil'])
      expect(() => client.url(bad)).toThrow();
  });
});
