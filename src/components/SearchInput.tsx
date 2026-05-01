import { useCallback, useEffect, useRef, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark } from "@fortawesome/free-solid-svg-icons";
import styles from "./SearchInput.module.css";

interface Props {
  onSearch: (query: string) => void;
  onFirstInput?: () => void;
  onClear?: () => void;
  disabled?: boolean;
  placeholder?: string;
  statusText?: string;
  externalValue?: string;
  hero?: boolean;
  clearTrigger?: number;
  initialValue?: string;
  focusOnMount?: boolean;
}

/**
 * Debounced search input that fires `onSearch` as the user types.
 */
export default function SearchInput({
  onSearch,
  onFirstInput,
  onClear,
  disabled = false,
  placeholder = "Ask anything…",
  statusText,
  externalValue,
  hero = false,
  clearTrigger,
  initialValue = "",
  focusOnMount = true,
}: Props): React.JSX.Element {
  const [value, setValue] = useState(initialValue);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const firstInputFiredRef = useRef(initialValue !== "");

  // Clear input when parent requests a reset
  useEffect(() => {
    if (!clearTrigger) return;
    setValue(""); // eslint-disable-line react-hooks/set-state-in-effect
    firstInputFiredRef.current = false;
    onSearch("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearTrigger]);

  // Sync when a suggestion is chosen externally
  useEffect(() => {
    if (externalValue === undefined) return;
    setValue(externalValue); // eslint-disable-line react-hooks/set-state-in-effect
    if (externalValue && !firstInputFiredRef.current) {
      firstInputFiredRef.current = true;
      onFirstInput?.();
    }
    onSearch(externalValue);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalValue]);

  const debouncedSearch = useCallback(
    (text: string) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        onSearch(text);
      }, 200);
    },
    [onSearch]
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const text = e.target.value;
    setValue(text);
    // Fire onFirstInput immediately on the very first non-empty keystroke
    if (text && !firstInputFiredRef.current) {
      firstInputFiredRef.current = true;
      onFirstInput?.();
    }
    debouncedSearch(text);
  };

  const handleClear = () => {
    setValue("");
    firstInputFiredRef.current = false;
    onSearch("");
    onClear?.();
  };

  const handleBlur = () => {
    // On iOS Safari, when input loses focus, scroll to ensure
    // video player is visible (since iOS auto-scrolls inputs into view)
    if (window.innerWidth < 900) {
      setTimeout(() => {
        window.scrollTo(0, 0);
      }, 100);
    }
  };

  return (
    <div className={styles.searchInputWrapper}>
      <input
        type="search"
        className={`${styles.searchInput}${hero ? ` ${styles.searchInputHero}` : ""}`}
        data-search-input
        value={value}
        onChange={handleChange}
        disabled={disabled}
        placeholder={placeholder}
        aria-label="Search astronaut questions"
        // eslint-disable-next-line jsx-a11y/no-autofocus
        autoFocus={focusOnMount}
        autoComplete="off"
        spellCheck={false}
        onBlur={handleBlur}
      />
      {statusText && !value && (
        <span className={styles.searchInputStatus} role="status" aria-live="polite">
          {statusText}
        </span>
      )}
      {value && (
        <button
          className={styles.searchClear}
          onClick={handleClear}
          aria-label="Clear search"
          type="button"
        >
          <FontAwesomeIcon icon={faXmark} />
        </button>
      )}
    </div>
  );
}
