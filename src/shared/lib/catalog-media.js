const demoResorts = new Set(["altun", "arasan", "bibi", "aktilek", "kokterek", "keremet"]);
const roomClasses = new Set(["standard", "comfort", "suite"]);

export function catalogMedia(item, kind, illustration) {
  const legacy = `/assets/${kind}.jpg`;
  const key = kind === "resort"
    ? (demoResorts.has(item.id) ? item.id : "")
    : (roomClasses.has(item.category) ? item.category : "");
  const fallback = key ? `/assets/catalog/${key}.jpg` : legacy;
  const placeholder = { kind: "image", url: fallback, alt: illustration };
  if (!item.media?.length) return [placeholder];
  return item.media.map((entry) =>
    entry.kind === "image" && entry.url === legacy ? placeholder : entry,
  );
}
