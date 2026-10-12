function ContinueButton({ show, onClick }) {
  return (
    <div className="mt-6 flex justify-end translate-x-[6vw]">
      {show && (
        <button
          className="border-2 border-neutral-200 bg-black px-6 py-2 text-lg hover:bg-neutral-200 hover:text-black"
          onClick={onClick}
        >
          Continue
        </button>
      )}
    </div>
  );
}

export default ContinueButton;