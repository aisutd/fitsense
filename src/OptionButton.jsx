function OptionButton({ label, selected, onClick }) {
  return (
    <button
      className={`border-2 border-neutral-200 px-6 py-2 text-left text-lg ${
        selected ? "bg-[#2bc20e] text-black" : "bg-black text-neutral-200"
      }`}
      onClick={onClick}
    >
      {selected && "✓ "}
      {label}
    </button>
  );
}

export default OptionButton;