import { useEffect, useState } from "react";
import FoodSearch from "./FoodSearch";
import {
  addMealItem,
  analyzeMeal,
  confirmMeal,
  deleteMealItem,
  discardMeal,
  listMeals,
  localToday,
  searchFoods,
  startMeal,
  updateMealItem,
  validationMessage,
} from "../api";

// Pick foods as you type (USDA search) or describe a meal in words -> review the ingredients -> confirm.
// Nutrition comes from USDA FoodData Central via the backend; nothing is estimated here.

const MEAL_TYPES = ["", "breakfast", "lunch", "dinner", "snack"];
const STEP = { g: 10, ml: 25, oz: 1, cup: 0.25, tbsp: 0.5, tsp: 0.5, count: 1, slice: 1, piece: 1, scoop: 0.5 };
const UNIT_LABEL = { count: "×", g: "g", oz: "oz", ml: "ml", cup: "cup", tbsp: "tbsp", tsp: "tsp", slice: "slice", piece: "piece", scoop: "scoop" };

const num = (n, digits = 0) => Number(n ?? 0).toLocaleString("en-US", { maximumFractionDigits: digits });
const unitKey = (unit) => unit ?? "count";

function Tag({ children, color }) {
  return (
    <span className="px-frame px-1.5 text-xs uppercase tracking-wider" style={{ "--frame": color, color }}>
      {children}
    </span>
  );
}

function FoodPicker({ item, onPick, busy }) {
  const [query, setQuery] = useState(item.ingredient_text);
  const [results, setResults] = useState(item.alternatives ?? []);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  async function search() {
    if (query.trim().length < 2) return;
    setSearching(true);
    setSearched(true);
    try {
      setResults(await searchFoods(query));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="mt-3 bg-night-900/70 p-3">
      <div className="flex gap-2">
        <div className="min-w-0 flex-1">
          <FoodSearch value={query} onChange={setQuery} onPick={(s) => onPick(s.fdc_id)} onEnter={search}
            label="Search USDA foods" className="py-1 text-lg" autoFocus />
        </div>
        <button type="button" onClick={search} className="px-focus px-3 text-cyan hover:underline" disabled={searching}>
          {searching ? "..." : "Search"}
        </button>
      </div>
      <ul className="mt-2 max-h-56 overflow-y-auto">
        {results.length === 0 && (
          <li className="py-1 text-muted">{searched ? "No matches. Try different words." : "Type to search USDA foods."}</li>
        )}
        {results.map((r) => (
          <li key={r.fdc_id}>
            <button
              type="button"
              disabled={busy}
              onClick={() => onPick(r.fdc_id)}
              className="px-focus flex w-full justify-between gap-3 py-1 text-left hover:text-cyan"
            >
              <span>{r.description}</span>
              <span className="shrink-0 text-muted">{r.calories_per_100g != null ? `${num(r.calories_per_100g)} kcal/100g` : ""}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ItemRow({ item, busy, onChange, onRemove }) {
  const [picking, setPicking] = useState(false);
  const unit = unitKey(item.unit);
  const options = Array.from(new Set([unit, ...(item.unit_options ?? [])])).filter((u) => STEP[u] || u === unit);
  const step = STEP[unit] ?? 1;
  const setQty = (q) => q > 0 && onChange({ quantity: Math.round(q * 100) / 100 });

  return (
    <li className="border-b-[3px] border-night-700 py-3 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-xl">
            {item.ingredient_text}
            {item.is_assumed && <Tag color="var(--color-gold)">assumed</Tag>}
            {item.needs_review && <Tag color="var(--color-nutrition)">check this</Tag>}
          </p>
          <p className="text-sm text-muted">
            {item.food ? item.food.description : "No USDA match yet"} · {item.portion_label}
          </p>
        </div>
        <p className="shrink-0 text-right">
          <span className="text-xl">{num(item.calories)}</span> <span className="text-muted">kcal</span>
          <br />
          <span className="text-sm text-muted">{item.grams != null ? `${num(item.grams, 1)} g` : ""}</span>
        </p>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" aria-label={`Less ${item.ingredient_text}`} disabled={busy || !item.food}
          onClick={() => setQty(Number(item.quantity) - step)} className="px-frame px-focus h-9 w-9 text-xl hover:text-cyan">−</button>
        <span className="min-w-12 text-center text-xl">{num(item.quantity, 2)}</span>
        <button type="button" aria-label={`More ${item.ingredient_text}`} disabled={busy || !item.food}
          onClick={() => setQty(Number(item.quantity) + step)} className="px-frame px-focus h-9 w-9 text-xl hover:text-cyan">+</button>
        <select
          value={unit}
          disabled={busy || !item.food}
          aria-label={`Unit for ${item.ingredient_text}`}
          onChange={(e) => onChange({ unit: e.target.value, quantity: e.target.value === "g" ? Math.round(item.grams ?? 100) : 1 })}
          className="px-frame cursor-pointer bg-night-900 px-2 py-1 text-lg"
        >
          {options.map((u) => (
            <option key={u} value={u}>{UNIT_LABEL[u] ?? u}</option>
          ))}
        </select>
        <span className="flex-1" />
        {item.needs_review && item.food && (
          <button type="button" disabled={busy} onClick={() => onChange({ fdc_id: item.food.fdc_id })} className="px-focus text-activity hover:underline">
            Looks right
          </button>
        )}
        <button type="button" onClick={() => setPicking((p) => !p)} className="px-focus text-cyan hover:underline">
          {picking ? "Close" : "Change food"}
        </button>
        <button type="button" disabled={busy} onClick={onRemove} className="px-focus text-muted hover:text-nutrition">
          Remove
        </button>
      </div>

      {picking && (
        <FoodPicker
          item={item}
          busy={busy}
          onPick={(fdcId) => {
            setPicking(false);
            onChange({ fdc_id: fdcId });
          }}
        />
      )}
    </li>
  );
}

function MealLogger({ userId, onLogged, onManual }) {
  const today = localToday();
  const [text, setText] = useState("");
  const [date, setDate] = useState(today);
  const [mealType, setMealType] = useState("");
  const [meal, setMeal] = useState(null);
  const [newItem, setNewItem] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  // Pick up an estimate that wasn't confirmed or discarded (e.g. the page was reloaded mid-review).
  useEffect(() => {
    let active = true;
    listMeals(userId, today, "estimated")
      .then((meals) => {
        const open = meals.at(-1);
        if (active && open) setMeal((current) => current ?? open);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [userId, today]);

  async function run(action, success) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await action();
      if (success) setMessage({ ok: true, text: success });
      return result;
    } catch (error) {
      setMessage({ ok: false, text: validationMessage(error, "Couldn't do that. Please try again.") });
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function analyze(event) {
    event?.preventDefault();
    if (text.trim().length < 2 || busy) return;
    const result = await run(() => analyzeMeal(userId, text.trim(), date, mealType));
    if (result) setMeal(result);
  }

  // A food picked from the dropdown starts the meal with exactly that USDA food.
  async function startWith(suggestion) {
    const m = await run(() => startMeal(userId, date, mealType, [{ fdc_id: suggestion.fdc_id }]));
    if (m) {
      setMeal(m);
      setText("");
    }
  }

  const change = (item, changes) => run(() => updateMealItem(meal.meal_id, item.meal_item_id, changes)).then((m) => m && setMeal(m));
  const remove = (item) => run(() => deleteMealItem(meal.meal_id, item.meal_item_id)).then((m) => m && setMeal(m));

  async function add(item) {
    const m = await run(() => addMealItem(meal.meal_id, item));
    if (m) {
      setMeal(m);
      setNewItem("");
    }
  }

  function addTyped(event) {
    event?.preventDefault();
    if (newItem.trim().length >= 2 && !busy) add({ text: newItem.trim() });
  }

  async function confirm() {
    const m = await run(() => confirmMeal(meal.meal_id), "Meal logged. HealthScore updated.");
    if (m) {
      setMeal(null);
      setText("");
      onLogged();
    }
  }

  async function discard() {
    const m = await run(() => discardMeal(meal.meal_id), "Discarded.");
    if (m) setMeal(null);
  }

  if (!meal) {
    return (
      <form onSubmit={analyze} className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div className="sm:col-span-2 lg:col-span-3">
          <p className="mb-1 text-sm uppercase tracking-wider text-muted" aria-hidden="true">What did you eat?</p>
          <FoodSearch
            multiline
            value={text}
            onChange={setText}
            onPick={startWith}
            onEnter={analyze}
            disabled={busy}
            label="What did you eat? Type a food to pick it, or describe the meal"
            placeholder="Greek yogurt… or: I had a 3-egg omelette and an iced coffee for breakfast"
            className="text-xl"
          />
          <p className="mt-1 text-sm text-muted">
            Type a food and pick it from the list, or describe the whole meal and press Enter.
          </p>
        </div>
        <label className="block">
          <span className="mb-1 block text-sm uppercase tracking-wider text-muted">Date</span>
          <input type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)}
            className="px-frame w-full bg-night-900/80 px-3 py-2 text-xl [color-scheme:dark]" />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm uppercase tracking-wider text-muted">Meal (optional)</span>
          <select value={mealType} onChange={(e) => setMealType(e.target.value)} className="px-frame w-full cursor-pointer bg-night-900/80 px-3 py-2 text-xl">
            {MEAL_TYPES.map((m) => (
              <option key={m} value={m} className="bg-night-900">{m ? m[0].toUpperCase() + m.slice(1) : "Detect from text"}</option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-end justify-end gap-4 sm:col-span-2 lg:col-span-1">
          <button type="button" onClick={onManual} className="px-focus text-muted hover:text-ink">Type totals instead</button>
          <button type="submit" disabled={busy || text.trim().length < 2}
            className={`px-button px-6 py-3 text-lg ${busy || text.trim().length < 2 ? "cursor-not-allowed bg-night-700 text-muted opacity-60" : "bg-nutrition text-night-950"}`}
            style={busy || text.trim().length < 2 ? { "--frame": "var(--color-night-500)", "--shadow": "var(--color-night-700)" } : { "--frame": "#ffffff", "--shadow": "var(--color-night-600)" }}>
            {busy ? "Analyzing..." : "Analyze ▶"}
          </button>
        </div>
        {message && <p role={message.ok ? "status" : "alert"} className={`sm:col-span-2 lg:col-span-3 ${message.ok ? "text-activity" : "text-nutrition"}`}>{message.text}</p>}
      </form>
    );
  }

  const t = meal.totals;
  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="font-title text-2xl font-bold text-nutrition">{meal.display_name}</h3>
        <p className="text-muted">{meal.raw_text ? `“${meal.raw_text}” · ` : ""}{meal.meal_type ?? "meal"} · {meal.log_date}</p>
      </div>
      <p className="mt-1 text-sm text-muted">Estimated from USDA FoodData Central. Adjust anything that's off, then confirm.</p>

      <ul className="mt-3">
        {meal.items.map((item) => (
          <ItemRow key={item.meal_item_id} item={item} busy={busy} onChange={(c) => change(item, c)} onRemove={() => remove(item)} />
        ))}
      </ul>

      <form onSubmit={addTyped} className="mt-3 flex gap-2">
        <div className="min-w-0 flex-1">
          <FoodSearch value={newItem} onChange={setNewItem} onPick={(s) => add({ fdc_id: s.fdc_id })} onEnter={addTyped}
            label="Add an ingredient" placeholder="Add an ingredient, e.g. 1 tbsp butter" className="text-lg" disabled={busy} />
        </div>
        <button type="submit" disabled={busy || newItem.trim().length < 2} className="px-focus px-3 text-cyan hover:underline">Add</button>
      </form>

      <div className="px-frame mt-5 grid grid-cols-2 gap-3 bg-night-900/70 p-4 sm:grid-cols-4">
        {[["Calories", t.calories, "kcal"], ["Protein", t.protein_g, "g"], ["Carbs", t.carbs_g, "g"], ["Fat", t.fat_g, "g"]].map(([label, value, unit]) => (
          <div key={label}>
            <p className="text-sm uppercase tracking-wider text-muted">{label}</p>
            <p className="text-2xl">{num(value, unit === "g" ? 1 : 0)} <span className="text-base text-muted">{unit}</span></p>
          </div>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-end gap-4">
        {message && <p role={message.ok ? "status" : "alert"} className={message.ok ? "text-activity" : "text-nutrition"}>{message.text}</p>}
        <button type="button" disabled={busy} onClick={discard} className="px-focus text-muted hover:text-nutrition">Discard</button>
        <button type="button" disabled={busy || meal.items.length === 0} onClick={confirm}
          className="px-button bg-activity px-6 py-3 text-lg text-night-950" style={{ "--frame": "#c9ffe0", "--shadow": "#1d7a48" }}>
          {busy ? "Saving..." : "Confirm meal ▶"}
        </button>
      </div>
    </div>
  );
}

export default MealLogger;
