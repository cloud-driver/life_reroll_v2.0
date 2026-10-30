'use client';
import { useLayoutEffect, useRef, type ReactNode } from 'react';
export function GameDialog({
  title,
  children,
  onClose,
  drawer = false,
  wide = false,
  guide,
  coachOnly = false,
}: {
  title: string;
  children?: ReactNode;
  onClose: () => void;
  drawer?: boolean;
  wide?: boolean;
  guide?: ReactNode;
  coachOnly?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null),
    close = useRef(onClose);
  close.current = onClose;
  useLayoutEffect(() => {
    const dialog = ref.current!,
      previous = document.activeElement as HTMLElement | null;
    dialog.showModal();
    return () => {
      dialog.close();
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  // Keep native scrolling available; only the coach can activate controls during a tour.
  return (
    <dialog
      ref={ref}
      className={`game-dialog ${drawer ? 'game-dialog-compact' : ''} ${wide ? 'game-dialog-wide' : ''} ${guide ? 'game-dialog-with-guide' : ''} ${coachOnly ? 'game-dialog-coach' : ''}`}
      aria-label={title}
      onCancel={e => {
        e.preventDefault();
        close.current();
      }}
    >
      {!coachOnly && (
        <>
          <header>
            <h2>{title}</h2>
            <button autoFocus={!guide} className="secondary" aria-label={`關閉${title}`} onClick={onClose}>
              關閉 ×
            </button>
          </header>
          <div className="game-dialog-body">
            <div
              className="game-dialog-page"
              aria-disabled={guide ? true : undefined}
              onPointerDownCapture={guide ? e => e.preventDefault() : undefined}
              onClickCapture={
                guide
                  ? e => {
                      e.preventDefault();
                      e.stopPropagation();
                    }
                  : undefined
              }
              onFocusCapture={
                guide
                  ? e => {
                      e.target.blur();
                      ref.current
                        ?.querySelector<HTMLButtonElement>('.tutorial-coach-actions button:last-child')
                        ?.focus();
                    }
                  : undefined
              }
              onKeyDownCapture={
                guide
                  ? e => {
                      e.preventDefault();
                      e.stopPropagation();
                    }
                  : undefined
              }
              onBeforeInputCapture={
                guide
                  ? e => {
                      e.preventDefault();
                      e.stopPropagation();
                    }
                  : undefined
              }
            >
              {children}
            </div>
          </div>
        </>
      )}
      {guide}
    </dialog>
  );
}
