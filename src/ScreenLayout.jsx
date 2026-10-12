import Background from "./backgroundA";
import { titlePattern } from "./patterns";

function ScreenLayout({ children }) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-black font-title text-neutral-200">
      <Background pattern={titlePattern} />
      <div className="relative z-10">{children}</div>
    </div>
  );
}

export default ScreenLayout;