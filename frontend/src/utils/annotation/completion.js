export function isAnnotationComplete(ann) {
  if (!ann) return false;
  return (
    ann.cognitiveMost &&
    ann.cognitiveLeast &&
    ann.affectiveMost &&
    ann.affectiveLeast &&
    ann.cognitiveMost !== ann.cognitiveLeast &&
    ann.affectiveMost !== ann.affectiveLeast
  );
}
