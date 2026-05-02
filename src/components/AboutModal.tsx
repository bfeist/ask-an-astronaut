import { useEffect, useRef } from "react";
import styles from "./AboutModal.module.css";

interface AboutModalProps {
  onClose: () => void;
}

export default function AboutModal({ onClose }: AboutModalProps): React.JSX.Element {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Focus the close button on mount
  useEffect(() => {
    closeBtnRef.current?.focus();
  }, []);

  // Trap focus within the modal
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = dialog.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const handleTab = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    dialog.addEventListener("keydown", handleTab);
    return () => dialog.removeEventListener("keydown", handleTab);
  }, []);

  return (
    <div
      className={styles.backdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="presentation"
    >
      <div
        ref={dialogRef}
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-label="About this project"
      >
        <button
          ref={closeBtnRef}
          className={styles.closeBtn}
          onClick={onClose}
          type="button"
          aria-label="Close"
        >
          ✕
        </button>

        <article className={styles.article}>
          <h2 className={styles.heading}>About This Project</h2>

          <figure className={styles.figure}>
            <img
              src="/images/IMG_1721_crop_small.jpg"
              alt="Astronaut aboard the International Space Station"
              className={styles.photo}
            />
          </figure>

          <p>
            <strong>Ask an Astronaut</strong> is a searchable archive of real questions asked of
            NASA astronauts during in-flight interviews, press conferences, and student Q&amp;A
            sessions aboard the International Space Station — spanning more than two decades of
            human spaceflight.
          </p>

          <p>
            Every question in the database was spoken by a real person — a student, a journalist, or
            a curious member of the public — and answered live from orbit. The archive draws from
            hundreds of hours of footage sourced from NASA&apos;s public video library on the
            Internet Archive.
          </p>

          <p>
            Rather than browsing by video, you can describe what you&apos;re curious about in your
            own words and the search engine finds the closest real question ever asked — then jumps
            you straight to that moment in the recording. The matching is done entirely in your
            browser using a local AI model, so no search query ever leaves your device.
          </p>

          <h3 className={styles.subheading}>How it works</h3>
          <p>
            Audio from each video is transcribed using WhisperX, then individual questions and
            answers are extracted and timestamped. Each question is converted into a semantic
            embedding — a numerical fingerprint of its meaning — using a compact transformer model.
            When you type a query, the same model runs locally in your browser and finds the
            questions whose embeddings are closest to yours.
          </p>

          <p>
            This project is part of{" "}
            <a href="https://issinrealtime.org" target="_blank" rel="noopener noreferrer">
              ISS in Real Time
            </a>
            , a collection of tools that bring the International Space Station closer to Earth.
          </p>
        </article>
      </div>
    </div>
  );
}
