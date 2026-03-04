import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  onSearch: (query: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * Debounced search input that fires `onSearch` as the user types.
 */
export default function SearchInput({
  onSearch,
  disabled = false,
  placeholder = "Ask anything…",
}: Props): React.JSX.Element {
  const [value, setValue] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    debouncedSearch(text);
  };

  const handleClear = () => {
    setValue("");
    onSearch("");
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
    <div className="search-input-wrapper">
      <input
        type="text"
        className="search-input"
        value={value}
        onChange={handleChange}
        disabled={disabled}
        placeholder={placeholder}
        // eslint-disable-next-line jsx-a11y/no-autofocus
        autoFocus
        spellCheck={false}
        onBlur={handleBlur}
      />
      {value && (
        <button
          className="search-clear"
          onClick={handleClear}
          aria-label="Clear search"
          type="button"
        >
          ×
        </button>
      )}
    </div>
  );
}
