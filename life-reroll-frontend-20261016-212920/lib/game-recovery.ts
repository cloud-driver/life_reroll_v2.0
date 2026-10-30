import type { RequestPlan } from './game-client';
import registry from './contracts/operations.json';
export type Recovery = { request?: RequestPlan; jobId?: string };
type StoragePort = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const PREFIX = 'life-reroll:recovery:v1:';
// Only gameplay requests are retained. Passwords, verification tokens and
// session/CSRF credentials must never be written to browser storage.
const operations = new Set([
  'C01',
  'C07',
  'C08',
  'C09',
  'C10',
  'C13',
  'D01',
  'D03',
  'D06',
  'D07',
  'D09',
  'D10',
  'D11',
  'E08',
  'E10',
  'E12',
  'F05',
  'F08',
  'F11',
  'G04',
  'G06',
]);
export class GameRecovery {
  constructor(
    private storage: StoragePort,
    private namespace = '',
  ) {}
  read(userId: string): Recovery | null {
    try {
      const raw = this.storage.getItem(PREFIX + this.namespace + ':' + userId);
      if (!raw) return null;
      const value = JSON.parse(raw);
      if (value.version !== 1 || value.userId !== userId) return null;
      const request = value.request as RequestPlan | undefined;
      if (request) {
        const op = registry.find(
          o =>
            operations.has(o.id) &&
            o.method === request.method &&
            new RegExp('^' + o.path.replace(/\{[^}]+\}/g, '[^/?]+') + '$').test(request.path),
        );
        if (!op || typeof request.key !== 'string' || !request.key) return null;
      }
      if (value.jobId !== undefined && typeof value.jobId !== 'string') return null;
      return { request, jobId: value.jobId };
    } catch {
      return null;
    }
  }
  save(userId: string, value: Recovery) {
    // A storage failure must block submission rather than silently lose the
    // only key able to resolve a committed request after a reload.
    this.storage.setItem(
      PREFIX + this.namespace + ':' + userId,
      JSON.stringify({ version: 1, userId, ...value }),
    );
  }
  begin(userId: string, operation: string, request: RequestPlan) {
    if (operations.has(operation)) this.save(userId, { request });
  }
  acknowledge(userId: string, jobId?: string) {
    if (jobId) this.save(userId, { jobId });
    else this.clear(userId);
  }
  clear(userId: string) {
    this.storage.removeItem(PREFIX + this.namespace + ':' + userId);
  }
}
