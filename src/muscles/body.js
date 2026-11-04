// The muscle body: skin volumes (blended into one smooth body) and muscle footprints that raise and
// groove the skin where they lie. Muscle names are the 17 groups the exercise data uses
// (primaryMuscles / secondaryMuscles in gym.json and home.json). Units are roughly meters; y is up,
// +z is the front. Built into public/models/muscle-body.bin by scripts/build-muscle-model.mjs.
//
// Proportions follow the 8-heads-tall figure (head 0.26): chin 1.44, nipples 1.18, navel and elbows
// 0.92, crotch and wrists 0.66, knees 0.15, soles -0.37. A lean, long-limbed, bald stylized figure.

export const GROUPS = [
  "chest", "shoulders", "traps", "lats", "middle back", "lower back", "abdominals", "neck", "biceps",
  "triceps", "forearms", "glutes", "abductors", "adductors", "quadriceps", "hamstrings", "calves",
];
// Painted details that aren't muscles: they get their own colors and are never highlighted.
export const DECOR = { eyes: 21, hand: 22 };

export function defineBody({ bell, bcap, m }) {
  // head: bald skull, jaw and chin, brow, nose; a short, solid neck
  bell([0, 1.58, -0.005], [0.096, 0.12, 0.11]);
  bell([0, 1.49, 0.028], [0.066, 0.056, 0.072]);
  bell([0, 1.457, 0.066], [0.03, 0.022, 0.03], 0.03);
  bell([0, 1.59, 0.082], [0.066, 0.02, 0.03], 0.03);
  bcap([0, 1.577, 0.097], [0, 1.533, 0.115], 0.011, 0.016, 0.02);
  bcap([0, 1.34, -0.005], [0, 1.46, 0.01], 0.058, 0.052);
  // torso: ribcage, belly, waist, pelvis
  bell([0, 1.13, -0.005], [0.2, 0.2, 0.12], 0.08);
  bell([0, 0.9, 0], [0.155, 0.14, 0.105], 0.1);
  bell([0, 0.78, -0.005], [0.15, 0.07, 0.1], 0.08);
  bell([0, 0.72, -0.005], [0.172, 0.1, 0.112], 0.08);

  for (const s of [1, -1]) {
    bell([s * 0.045, 1.532, 0.073], [0.03, 0.024, 0.03], 0.04);
    bell([s * 0.097, 1.555, 0], [0.014, 0.032, 0.024], 0.02);
    // arms (elbow at the navel, wrist at the crotch), hands palm-forward like an anatomy chart
    bell([s * 0.245, 1.25, 0], [0.06, 0.06, 0.06], 0.08);
    bcap([s * 0.275, 1.24, 0], [s * 0.335, 0.94, 0], 0.052, 0.043);
    bcap([s * 0.34, 0.92, 0], [s * 0.395, 0.665, 0.02], 0.044, 0.031);
    bell([s * 0.405, 0.6, 0.022], [0.032, 0.042, 0.016], 0.03);
    bell([s * 0.407, 0.53, 0.026], [0.033, 0.046, 0.014], 0.025, [0.15, 0, 0]);
    bcap([s * 0.433, 0.61, 0.026], [s * 0.455, 0.565, 0.036], 0.012, 0.01, 0.02);
    // legs: full at the hip, tapering to the knee; calves and feet
    bcap([s * 0.11, 0.68, 0], [s * 0.115, 0.17, 0.01], 0.1, 0.058);
    bcap([s * 0.115, 0.15, 0.01], [s * 0.115, -0.3, -0.01], 0.056, 0.034);
    bell([s * 0.115, -0.345, 0.045], [0.045, 0.03, 0.1]);

    // face and hand details
    m("eyes", [s * 0.034, 1.562, 0.094], [0.011, 0.007, 0.03], null, -0.003);
    [-0.024, -0.008, 0.008, 0.024].forEach((dx) => m("hand", [s * (0.407 + dx), 0.52, 0.03], [0.01, 0.04, 0.03], [0.15, 0, 0], 0.003));
    m("hand", [s * 0.405, 0.6, 0.022], [0.025, 0.03, 0.03], null, 0.002);

    // chest and core
    m("chest", [s * 0.1, 1.17, 0.085], [0.11, 0.08, 0.07], [0, 0, s * -0.15], 0.022);
    m("chest", [s * 0.09, 1.245, 0.075], [0.09, 0.045, 0.06], [0, 0, s * 0.12], 0.016);
    [0, 1, 2].forEach((i) => m("abdominals", [s * 0.165, 1.06 - i * 0.04, 0.06], [0.04, 0.02, 0.06], [0, s * 0.5, s * -0.5], 0.01));
    [1.065, 0.98, 0.895].forEach((y) => m("abdominals", [s * 0.046, y, 0.08], [0.05, 0.048, 0.06], null, 0.014));
    m("abdominals", [s * 0.046, 0.8, 0.075], [0.048, 0.06, 0.06], null, 0.014);
    m("abdominals", [s * 0.04, 0.715, 0.075], [0.04, 0.045, 0.06], null, 0.008);
    m("abdominals", [s * 0.125, 0.9, 0.04], [0.06, 0.11, 0.08], [0, s * 0.6, s * 0.1], 0.012);
    m("abdominals", [s * 0.12, 0.775, 0.045], [0.05, 0.055, 0.07], [0, s * 0.5, s * -0.35], 0.01);
    m("neck", [s * 0.035, 1.395, 0.02], [0.035, 0.06, 0.06], [0.25, 0, s * 0.3], 0.006);
    // deltoids: front, side and rear heads tapering to a point down the outside of the arm
    m("shoulders", [s * 0.265, 1.24, 0.045], [0.05, 0.09, 0.06], [0, 0, s * 0.3], 0.02);
    m("shoulders", [s * 0.31, 1.17, 0], [0.05, 0.13, 0.07], [0, 0, s * 0.15], 0.02);
    m("shoulders", [s * 0.265, 1.24, -0.045], [0.05, 0.09, 0.06], [0, 0, s * 0.3], 0.02);
    // back
    m("traps", [s * 0.09, 1.335, -0.03], [0.1, 0.05, 0.07], [0, 0, s * -0.45], 0.016);
    m("middle back", [s * 0.11, 1.12, -0.095], [0.09, 0.1, 0.06], [0, 0, s * -0.1], 0.014);
    m("lats", [s * 0.14, 0.98, -0.07], [0.09, 0.19, 0.07], [0, s * -0.3, s * 0.2], 0.016);
    m("lower back", [s * 0.045, 0.83, -0.09], [0.035, 0.18, 0.05], null, 0.014);
    // arms
    m("biceps", [s * 0.305, 1.08, 0.04], [0.045, 0.12, 0.05], [0, 0, s * 0.2], 0.018);
    m("biceps", [s * 0.335, 0.97, 0.02], [0.025, 0.045, 0.04], [0, 0, s * 0.2], 0.01);
    m("triceps", [s * 0.305, 1.1, -0.04], [0.047, 0.13, 0.05], [0, 0, s * 0.2], 0.016);
    m("triceps", [s * 0.35, 1.11, -0.01], [0.028, 0.075, 0.04], [0, 0, s * 0.2], 0.014);
    m("forearms", [s * 0.375, 0.81, -0.005], [0.045, 0.1, 0.04], [0, 0, s * 0.17], 0.014);
    m("forearms", [s * 0.35, 0.77, 0.025], [0.04, 0.11, 0.04], [0, 0, s * 0.17], 0.012);
    // hips: glute max, glute med and TFL on the side, hip flexors in front up to the crease
    m("glutes", [s * 0.1, 0.68, -0.085], [0.105, 0.1, 0.08], null, 0.022);
    m("abductors", [s * 0.17, 0.76, -0.04], [0.055, 0.06, 0.06], [0, 0, s * -0.3], 0.014);
    m("abductors", [s * 0.175, 0.7, 0.035], [0.035, 0.07, 0.06], [0, 0, s * 0.15], 0.01);
    m("quadriceps", [s * 0.11, 0.66, 0.075], [0.05, 0.05, 0.06], [0, 0, s * -0.3], 0.01);
    // thighs: rectus femoris, vastus lateralis, vastus medialis (teardrop), sartorius, adductors
    m("quadriceps", [s * 0.11, 0.43, 0.065], [0.048, 0.19, 0.065], null, 0.018);
    m("quadriceps", [s * 0.17, 0.37, 0.025], [0.048, 0.2, 0.075], [0, 0, s * 0.05], 0.018);
    m("quadriceps", [s * 0.075, 0.23, 0.055], [0.048, 0.08, 0.055], null, 0.018);
    m("quadriceps", [s * 0.09, 0.49, 0.055], [0.018, 0.2, 0.05], [0, 0, s * -0.35], 0.008);
    m("adductors", [s * 0.05, 0.52, 0.01], [0.05, 0.16, 0.075], [0, 0, s * -0.1], 0.014);
    // hamstrings: fleshy under the glute, then tendons that split toward the knee (biceps femoris to
    // the outside, semitendinosus/semimembranosus to the inside), leaving the hollow behind the knee
    m("hamstrings", [s * 0.12, 0.45, -0.065], [0.047, 0.15, 0.065], [0, 0, s * 0.12], 0.018);
    m("hamstrings", [s * 0.156, 0.255, -0.055], [0.018, 0.07, 0.05], [0, 0, s * 0.35], 0.012);
    m("hamstrings", [s * 0.078, 0.45, -0.065], [0.045, 0.15, 0.065], [0, 0, s * -0.04], 0.018);
    m("hamstrings", [s * 0.066, 0.255, -0.055], [0.018, 0.07, 0.05], [0, 0, s * -0.2], 0.012);
    // calves: the two gastrocnemius heads close the bottom of that hollow, soleus below them
    m("calves", [s * 0.132, 0.07, -0.04], [0.04, 0.11, 0.065], [0, 0, s * -0.08], 0.018);
    m("calves", [s * 0.09, 0.06, -0.04], [0.044, 0.12, 0.065], [0, 0, s * 0.08], 0.02);
    m("calves", [s * 0.115, -0.08, -0.025], [0.05, 0.08, 0.055], null, 0.01);
  }
  m("traps", [0, 1.2, -0.1], [0.05, 0.14, 0.05], null, 0.012);
}
