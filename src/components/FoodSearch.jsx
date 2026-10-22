import { useEffect, useId, useRef, useState } from "react";
import { suggestFoods } from "../api";

// Search-as-you-type over USDA foods (served from the backend's local copy, so it's fast).
// Foods from our list come first with friendly names, then USDA matches. Picking one calls
// onPick(suggestion); Enter with nothing highlighted calls onEnter() (e.g. analyze a sentence).

const DEBOUNCE_MS = 150;
const MAX_WORDS = 6; // longer text is a sentence to analyze, not a food name
const cache = new Map(); // query -> suggestions, for this page session

const SOURCE_LABEL = { "Survey (FNDDS)": "USDA survey", "SR Legacy": "USDA SR", Foundation: "USDA foundation" };

function FoodSearch({ value, onChange, onPick, onEnter, multiline = false, label, placeholder, className = "", disabled, autoFocus }) {
  const id = useId();
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const typed = useRef(false); // only search after the player types, not when the value is set for them

  const query = value.trim();
  const searchable = query.length >= 2 && query.split(/\s+/).length <= MAX_WORDS;

  useEffect(() => {
    if (!typed.current || !searchable) {
      setResults([]);
      setLoading(false);
      return;
    }
    const key = query.toLowerCase();
    if (cache.has(key)) {
      setResults(cache.get(key));
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      suggestFoods(query, controller.signal)
        .then((found) => {
          cache.set(key, found);
          setResults(found);
          setActive(-1);
        })
        .catch((error) => {
          if (error.name !== "AbortError") setResults([]);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, searchable]);

  function pick(suggestion) {
    typed.current = false;
    setOpen(false);
    setResults([]);
    setActive(-1);
    onPick(suggestion);
  }

  function onKeyDown(e) {
    const showing = open && results.length > 0;
    if (e.key === "ArrowDown" && showing) {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp" && showing) {
      e.preventDefault();
      setActive((a) => (a <= 0 ? results.length - 1 : a - 1));
    } else if (e.key === "Enter" && !e.shiftKey) {
      if (showing && active >= 0) {
        e.preventDefault();
        pick(results[active]);
      } else if (onEnter) {
        e.preventDefault();
        setOpen(false);
        onEnter();
      }
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      setOpen(false);
    }
  }

  const Input = multiline ? "textarea" : "input";
  const listId = `${id}-list`;
  const showList = open && searchable && (results.length > 0 || loading);

  return (
    <div className="relative">
      <Input
        role="combobox"
        aria-label={label}
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && active >= 0 ? `${id}-${active}` : undefined}
        value={value}
        disabled={disabled}
        autoFocus={autoFocus}
        placeholder={placeholder}
        maxLength={multiline ? 500 : 200}
        rows={multiline ? 2 : undefined}
        onChange={(e) => {
          typed.current = true;
          setOpen(true);
          onChange(e.target.value);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className={`px-frame w-full bg-night-900/80 px-3 py-2 text-ink outline-none placeholder:text-night-500 focus:[--frame:var(--color-cyan)] ${multiline ? "resize-y" : ""} ${className}`}
      />
      {showList && (
        <ul id={listId} role="listbox" aria-label="Matching foods"
          className="px-frame absolute left-0 right-0 top-full z-30 mt-1 max-h-80 overflow-y-auto bg-night-900 py-1 shadow-xl [color-scheme:dark]">
          {results.length === 0 && <li className="px-3 py-2 text-muted">Searching USDA foods…</li>}
          {results.map((r, i) => (
            <li
              key={r.fdc_id}
              id={`${id}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()} // keep focus so the click lands
              onMouseMove={() => active !== i && setActive(i)} // not mouseenter: a list opening under a still pointer shouldn't move the highlight
              onClick={() => pick(r)}
              className={`flex cursor-pointer items-start justify-between gap-3 px-3 py-1.5 ${i === active ? "bg-night-700 text-cyan" : ""}`}
            >
              <span className="min-w-0">
                <span className="block truncate text-lg">{r.name}</span>
                <span className="block truncate text-sm text-muted">
                  {r.source === "list" ? r.description : SOURCE_LABEL[r.data_type] ?? r.data_type}
                </span>
              </span>
              <span className="shrink-0 pt-1 text-sm text-muted">
                {r.calories_per_100g != null ? `${Math.round(r.calories_per_100g)} kcal/100g` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default FoodSearch;
