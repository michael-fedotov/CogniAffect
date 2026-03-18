export function generateAnnotatorId() {
  const num = Math.floor(Math.random() * 900) + 100;
  return `ANNO_${String(num).padStart(3, '0')}`;
}
