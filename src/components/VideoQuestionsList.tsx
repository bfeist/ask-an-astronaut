import { useEffect, useMemo, useRef } from "react";
import { getQuestionsForVideo } from "@/lib/searchEngine";

interface Props {
  /** The source_file identifier for the current video. */
  sourceFile: string;
  /** The currently active question ID (highlighted in the list). */
  activeQuestionId: number;
  /** Called when the user clicks a different question. */
  onSeek: (question: IndexQuestion) => void;
}

function formatTime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Displays all Q&A pairs from a single video, highlighting the
 * currently-playing question. Clicking a row seeks the video.
 */
export default function VideoQuestionsList({
  sourceFile,
  activeQuestionId,
  onSeek,
}: Props): React.JSX.Element {
  const questions = useMemo(() => getQuestionsForVideo(sourceFile), [sourceFile]);
  const activeRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Scroll the active question into view within the list container only
  useEffect(() => {
    const item = activeRef.current;
    const list = listRef.current;
    if (!item || !list) return;
    const itemTop = item.offsetTop;
    const itemBottom = itemTop + item.offsetHeight;
    const listTop = list.scrollTop;
    const listBottom = listTop + list.clientHeight;
    if (itemTop < listTop) {
      list.scrollTop = itemTop;
    } else if (itemBottom > listBottom) {
      list.scrollTop = itemBottom - list.clientHeight;
    }
  }, [activeQuestionId]);

  if (questions.length <= 1) {
    return <></>;
  }

  return (
    <div className="video-questions">
      <div className="video-questions-header">Questions in this video ({questions.length})</div>
      <div className="video-questions-list" ref={listRef}>
        {questions.map((q, i) => {
          const isActive = q.id === activeQuestionId;
          return (
            <button
              key={q.id}
              ref={isActive ? activeRef : null}
              className={`vq-item ${isActive ? "vq-item-active" : ""}`}
              onClick={() => onSeek(q)}
              type="button"
            >
              <div className="vq-rank">{i + 1}</div>
              <div className="vq-body">
                <div className="vq-text">{q.text}</div>
                <div className="vq-meta">
                  <span className="vq-time">Q @ {formatTime(q.question_start)}</span>
                  <span className="vq-event">{q.event_type.replace(/_/g, " ")}</span>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
