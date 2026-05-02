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
            sessions aboard the International Space Station, spanning more than two decades of human
            spaceflight.
          </p>

          <p>
            This website was built by&nbsp;
            <a href="https://benfeist.com" target="_blank" rel="noopener noreferrer">
              Ben Feist
            </a>{" "}
            and{" "}
            <a href="https://davidcharney.com" target="_blank" rel="noopener noreferrer">
              David Charney
            </a>
            , contractors at NASA and the creators of&nbsp;
            <a href="https://issinrealtime.org" target="_blank" rel="noopener noreferrer">
              ISS in Real Time
            </a>{" "}
            and{" "}
            <a href="https://apolloinrealtime.org" target="_blank" rel="noopener noreferrer">
              Apollo in Real Time
            </a>
            .
          </p>
          <p>
            While sorting through ISS data, we became aware of the vast number of Q&amp;A sessions
            conducted with crews aboard the International Space Station and began to wonder: has
            every question you could ask an astronaut already been asked?
          </p>

          <p>
            Every question in this archive was spoken by a real person: a student, a journalist, or
            a curious member of the public. Each one was answered live from orbit. The archive draws
            from hundreds of hours of footage sourced from NASA&apos;s public video library on the
            Internet Archive.
          </p>

          <p>
            Modern AI tools made it possible to repurpose these thousands of recorded exchanges into
            something new. Rather than browsing video by video, you can describe what you&apos;re
            curious about in your own words, and the search engine finds the closest real question
            ever asked. It then jumps you straight to that moment in the recording.
          </p>

          <p>
            The matching is done entirely in your browser using a local AI model, so no search query
            ever leaves your device.
          </p>

          <h3 className={styles.subheading}>How it works</h3>

          <p>
            Building this archive required assembling a pipeline that could automatically sift
            through thousands of hours of NASA footage, identify where real questions were asked and
            answered, and make every exchange searchable by meaning rather than by keyword. Here is
            how each stage works.
          </p>

          <h4 className={styles.subheading2}>1. Discovering the videos</h4>
          <p>
            NASA&apos;s Johnson Space Center regularly uploads footage to the{" "}
            <a href="https://archive.org" target="_blank" rel="noopener noreferrer">
              Internet Archive
            </a>
            , a public nonprofit digital library. A custom harvester scans the Archive&apos;s API,
            collecting metadata--titles, descriptions, filenames, and subject tags--for every video
            ever uploaded by the NASA JSC public affairs office. This produces a catalog of many
            thousands of candidate recordings.
          </p>

          <h4 className={styles.subheading2}>2. Identifying Q&amp;A sessions</h4>
          <p>
            Most of that footage is not what we need: rocket launches, spacewalk replays, crew
            arrival ceremonies. Before downloading anything, each video&apos;s metadata is fed to a
            locally running large language model (gemma3:12b) which decides whether the recording is
            likely to contain a real Q&amp;A session with astronauts. Videos with strong signals
            against ISS content--Apollo missions, Artemis launches, Hubble operations--are filtered
            out first using keyword rules and a database of ISS crew surnames, so the LLM only needs
            to evaluate genuinely ambiguous cases.
          </p>

          <h4 className={styles.subheading2}>3. Transcription and speaker identification</h4>
          <p>
            The remaining videos are downloaded and processed by WhisperX, a high-accuracy
            speech-to-text system built on OpenAI&apos;s Whisper model, with forced phoneme
            alignment to produce word-level timestamps accurate to a fraction of a second. Before
            transcription begins, a multi-point language detection pass samples audio from several
            places throughout each file--not just the opening seconds--to reliably detect
            non-English content and skip it. Speaker diarization is then applied to label each
            segment with a speaker ID, which is essential for the next step.
          </p>

          <h4 className={styles.subheading2}>4. Extracting questions and answers</h4>
          <p>
            Extracting Q&amp;A pairs from a raw transcript is harder than it sounds. A two-pass
            approach is used. In the first pass, lightweight text rules scan every transcript
            segment for question marks and interrogative words, producing a list of candidate
            anchors. In the second pass, a focused context window around each candidate--roughly
            twenty seconds before and ninety seconds after--is sent to the LLM with the candidate
            highlighted. The LLM answers one narrow question: is this a real question directed at an
            astronaut, with a response from a different speaker? If yes, it returns the precise
            start and end timestamps for both the question and the answer. These independent calls
            are run in parallel across the transcript to keep processing time reasonable.
          </p>

          <h4 className={styles.subheading2}>5. Building the search index</h4>
          <p>
            Once all Q&amp;A pairs are extracted and timestamped, each question is converted into a
            semantic embedding--a list of 384 numbers that encodes the meaning of the
            sentence--using the all-MiniLM-L6-v2 sentence transformer model. The embeddings are
            stored in a compact binary file using 16-bit floats. The result is a small set of static
            files that ship with the website: question text and video timestamps in one file, raw
            embedding vectors in another.
          </p>

          <h4 className={styles.subheading2}>6. Searching in your browser</h4>
          <p>
            When you type a query, the same all-MiniLM-L6-v2 model, compiled to WebAssembly, runs
            entirely within your browser tab. It converts your query into a matching 384-dimensional
            embedding and computes cosine similarity against every stored question. The closest
            matches are returned instantly, with no search query ever sent to a server.
          </p>
        </article>
      </div>
    </div>
  );
}
