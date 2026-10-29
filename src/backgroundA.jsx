import { GRID } from "./patterns";

const COLORS = {
  mint: "#6BE29A",
  offwhite: "#E6E6E6",
};

function Background({ pattern }) {
  return (
    <div
      aria-hidden="true"
      className="absolute inset-0 bg-black"
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${GRID.columns}, 1fr)`,
        gridTemplateRows: `repeat(${GRID.rows}, 1fr)`,
      }}
    >
      {pattern.map((block, index) => (
        <div
          key={index}
          style={{
            backgroundColor: COLORS[block.color],
            gridColumn: `${block.col} / span ${block.colSpan}`,
            gridRow: `${block.row} / span ${block.rowSpan}`,
          }}
        />
      ))}
    </div>
  );
}

export default Background;