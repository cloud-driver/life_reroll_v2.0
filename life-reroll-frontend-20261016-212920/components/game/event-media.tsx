'use client';
import { useEffect, useState } from 'react';
import {
  EVENT_MEDIA_READY,
  resolveEventMedia,
  type EventMediaAsset,
  type EventMediaManifest,
} from '@/lib/event-media';
import type { Event } from '@/lib/game-types';
let manifestRequest: Promise<EventMediaManifest> | undefined;
function loadManifest() {
  return (manifestRequest ??= fetch('/event-media.json')
    .then(r => {
      if (!r.ok) throw Error('media unavailable');
      return r.json() as Promise<EventMediaManifest>;
    })
    .catch(e => {
      manifestRequest = undefined;
      throw e;
    }));
}
export function EventMedia({
  event,
  runId,
  asset: override,
}: {
  event: Event;
  runId: string;
  asset?: EventMediaAsset;
}) {
  const [manifest, setManifest] = useState<EventMediaManifest>({}),
    [failed, setFailed] = useState(false);
  const asset = override ?? resolveEventMedia(manifest, event);
  useEffect(() => {
    let active = true;
    void loadManifest()
      .then(value => {
        if (active) setManifest(value);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => setFailed(false), [asset?.src, event.id]);
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent(EVENT_MEDIA_READY, {
        detail: {
          run_id: runId,
          event_id: event.id,
          visual_key: event.visual_key ?? null,
          kind: event.kind,
          occurred_on: event.occurred_on,
          status: event.status,
        },
      }),
    );
  }, [runId, event.id, event.visual_key, event.kind, event.occurred_on, event.status]);
  return (
    <figure
      className="event-media-slot"
      data-event-id={event.id}
      data-visual-key={event.visual_key ?? ''}
      aria-label="事故情境圖片"
    >
      {asset && !failed ? (
        <img decoding="async" src={asset.src} alt={asset.alt} onError={() => setFailed(true)} />
      ) : (
        <div className="event-media-placeholder">
          <span aria-hidden="true">◇</span>
          <strong>事件情境圖片預留區</strong>
          <small>圖片尚未接入，事件與保險流程可正常操作。</small>
        </div>
      )}
    </figure>
  );
}
