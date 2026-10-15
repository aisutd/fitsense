// Pixel-art icons. Each row is a string; every character is one pixel and maps
// to a colour in `colors`. "." is transparent. Render them with <PixelIcon />.

export const ICONS = {
  apple: {
    colors: { r: "#ff5d6c", d: "#c23447", w: "#ffd1d6", g: "#42e08b", b: "#8a5a32" },
    art: [
      "......b.gg..",
      "......bggg..",
      "...rr.b.rr..",
      "..rrrrrrrrr.",
      ".rwwrrrrrrrr",
      ".rwrrrrrrrrr",
      ".rrrrrrrrrrr",
      ".rrrrrrrrrrd",
      ".rrrrrrrrrdd",
      "..rrrrrrrdd.",
      "...rrd.rdd..",
    ],
  },

  dumbbell: {
    colors: { b: "#4d8dff", d: "#2c5fc4", l: "#b9cdf0" },
    art: [
      ".bb......bb.",
      "bbbb....bbbb",
      "bbbb....bbbb",
      "bbbbllllbbbb",
      "bbbbllllbbbb",
      "dddd....dddd",
      "dddd....dddd",
      ".dd......dd.",
    ],
  },

  moon: {
    colors: { p: "#a66bff", d: "#7443c9", s: "#e0ccff" },
    art: [
      "....ppp.....",
      "..pppp....s.",
      ".ppp.......",
      ".ppp.......s",
      "pppp........",
      "pppp........",
      "pppd........",
      "pppdd.......",
      ".pppdd....d.",
      ".ppppddddd..",
      "..pppppdd...",
      "....ppp.....",
    ],
  },

  runner: {
    colors: { g: "#42e08b", d: "#22a862" },
    art: [
      "......gg....",
      "......gg....",
      "...ggggg....",
      "..g..ggg.gg.",
      ".g...gg.....",
      ".....ggg....",
      "....gg.gg...",
      "...gg...dd..",
      "..dd.....d..",
      ".dd......d..",
      "dd.......dd.",
    ],
  },

  trophy: {
    colors: { y: "#f7b733", o: "#c4831a", w: "#fff1c4", b: "#8a5a32" },
    art: [
      "..yyyyyyyy..",
      "yyywyyyyyoyy",
      "y.ywyyyyyo.y",
      "y.ywyyyyyo.y",
      ".yyyyyyyoyy.",
      "...yyyyoo...",
      "....yyoo....",
      ".....yo.....",
      ".....yo.....",
      "...oooooo...",
      "...bbbbbb...",
      "..bbbbbbbb..",
    ],
  },

  calendar: {
    colors: { c: "#4fd8ff", d: "#2a8fb3", w: "#e8edff" },
    art: [
      "..d....d....",
      ".cdccccdccc.",
      ".cccccccccc.",
      ".c........c.",
      ".c.w.w.w..c.",
      ".c........c.",
      ".c.w.w.w..c.",
      ".c........c.",
      ".cccccccccc.",
    ],
  },

  player: {
    colors: { s: "#ffcf9e", h: "#8a5a32", c: "#4fd8ff", d: "#2a8fb3" },
    art: [
      "...hhhhhh...",
      "..hhhhhhhh..",
      "..hssssssh..",
      "..ss.ss.ss..",
      "..ssssssss..",
      "...ssssss...",
      ".cccccccccc.",
      "cccccccccccc",
      "ss.cccccc.ss",
      "...dd..dd...",
      "...dd..dd...",
    ],
  },

  hourglass: {
    colors: { o: "#c4831a", y: "#f7b733", g: "#e8edff" },
    art: [
      "oooooooooo",
      ".g......g.",
      ".gyyyyyyg.",
      "..gyyyyg..",
      "...gyyg...",
      "....gg....",
      "....gg....",
      "...g..g...",
      "..g.yy.g..",
      ".gyyyyyyg.",
      "oooooooooo",
    ],
  },

  kettlebell: {
    colors: { k: "#94a3c8", d: "#5d6b91", w: "#e8edff" },
    art: [
      "...kkkkkk...",
      "..kk....kk..",
      "..k......k..",
      "..kk....kk..",
      ".kkkkkkkkkk.",
      "kkwkkkkkkkkk",
      "kwkkkkkkkkkk",
      "kkkkkkkkkkkd",
      "kkkkkkkkkkdd",
      ".kkkkkkkddd.",
      "..dddddddd..",
    ],
  },

  ruler: {
    colors: { y: "#f7b733", o: "#8a5a32" },
    art: [
      "yyyyyy",
      "yooooy",
      "yyyyyy",
      "yyyooy",
      "yyyyyy",
      "yooooy",
      "yyyyyy",
      "yyyooy",
      "yyyyyy",
      "yooooy",
      "yyyyyy",
    ],
  },

  flame: {
    colors: { r: "#ff5d6c", o: "#ff9a3c", y: "#ffe066" },
    art: [
      ".....r......",
      ".....rr.....",
      "....rrr.....",
      "....rrrr..r.",
      "...rrrrr.rr.",
      "..rrrorrrrr.",
      "..rroooorrr.",
      ".rrooyyoorr.",
      ".rroyyyyorr.",
      ".rroyyyyorr.",
      "..rroyyorr..",
      "...rrrrrr...",
    ],
  },

  heart: {
    colors: { r: "#ff5d6c", d: "#c23447", w: "#ffd1d6" },
    art: [
      ".rrr...rrr.",
      "rrrrr.rrrrr",
      "rwwrrrrrrrr",
      "rwrrrrrrrrr",
      "rrrrrrrrrrd",
      ".rrrrrrrrd.",
      "..rrrrrrd..",
      "...rrrrd...",
      "....rrd....",
      ".....d.....",
    ],
  },

  star: {
    colors: { y: "#f7b733", o: "#c4831a", w: "#fff1c4" },
    art: [
      ".....y.....",
      "....yyy....",
      "....ywy....",
      "yyyyywyyyyy",
      ".yyyyyyyyy.",
      "..yyyyyyy..",
      "...yyyyy...",
      "..yyyoyyy..",
      "..yyo.oyy..",
      ".yo.....oy.",
    ],
  },

  house: {
    colors: { r: "#ff5d6c", d: "#c23447", w: "#e8edff", g: "#94a3c8", y: "#ffe066", b: "#8a5a32" },
    art: [
      ".....rr.....",
      "....rrrr....",
      "...rrrrrr...",
      "..rrrrrrrr..",
      ".rrrrrrrrrr.",
      "dddddddddddd",
      ".wwwwwwwwww.",
      ".wyywwwbbww.",
      ".wyywwwbbww.",
      ".wwwwwwbbww.",
      ".gggggggggg.",
    ],
  },

  swap: {
    colors: { g: "#42e08b", c: "#4fd8ff" },
    art: [
      ".......g....",
      ".......gg...",
      ".gggggggggg.",
      ".......gg...",
      ".......g....",
      "............",
      "....c.......",
      "...cc.......",
      ".cccccccccc.",
      "...cc.......",
      "....c.......",
    ],
  },
};

// Signal-bar style icon for fitness level: `filled` of 3 bars lit.
export function levelIcon(filled, color = "#42e08b") {
  const rows = [];
  for (let row = 0; row < 9; row += 1) {
    let line = "";
    for (let bar = 0; bar < 3; bar += 1) {
      const top = 6 - bar * 3; // bar heights 3, 6, 9
      const ch = row >= top ? (bar < filled ? "a" : "o") : ".";
      line += ch + ch + ch + (bar < 2 ? "." : "");
    }
    rows.push(line);
  }
  return { colors: { a: color, o: "#26345a" }, art: rows };
}
