export function fisherYates(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function generateShuffleMaps(scenarios) {
  const maps = {};
  scenarios.forEach((s) => {
    maps[s.scenario_id] = fisherYates([0, 1, 2]);
  });
  return maps;
}
