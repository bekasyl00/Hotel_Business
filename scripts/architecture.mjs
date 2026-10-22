import { writeFile } from "node:fs/promises";
import { graph, slice } from "./source-graph.mjs";
const { files, edges } = await graph();
const slices = [...new Set(files.map(slice))];
const id = (s) => s.replaceAll(/[^a-zA-Z0-9_]/g, "_");
const notes = {
  app: "Инициализация Vue, Router, Pinia; выбор HTTP или локального демо-адаптера.",
  "pages/catalog":
    "Гостевой сайт: поиск, карта, комнаты, тарифы и собственные брони.",
  "pages/workspace": "Кабинет: реестры, фильтры, действия и история изменений.",
  "pages/login": "Выбор демо-аккаунта или форма серверного входа в режиме api.",
  "entities/session": "Pinia: текущий пользователь и роль.",
  "entities/resort": "Pinia: санатории, физические комнаты и тарифы.",
  "entities/booking": "Pinia: брони и чистые правила дат.",
  "shared/api":
    "Контракт транспорта, ошибки, HTTP fetch с cookies и сохранение форм.",
  "shared/ui": "Общие native dialog и карта Leaflet.",
  "shared/lib": "Форматирование дат, сумм и подписей.",
  "shared/config": "Режим demo/api и адрес API.",
};
const lines = [
  "// GENERATED from actual .js/.vue imports by npm run arch:sync.",
  "specification { element module }",
  "model {",
];
for (const s of slices) {
  lines.push(
    `  ${id(s)} = module '${s}' {`,
    `    description '${notes[s] || "Компоненты и действия среза " + s}. Файлов: ${files.filter((f) => slice(f) === s).length}'`,
    `    link https://github.com/bekasyl00/Hotel_Business/tree/main/src/${s} 'Исходный код'`,
    "  }",
  );
}
const links = new Set(
  edges
    .map((e) => [slice(e.from), slice(e.to)].join("|"))
    .filter((e) => {
      const [a, b] = e.split("|");
      return a !== b;
    }),
);
for (const link of links) {
  const [a, b] = link.split("|");
  lines.push(`  ${id(a)} -> ${id(b)} 'import'`);
}
lines.push(
  "}",
  "views {",
  "  view modules {",
  "    title 'FSD: реальные зависимости срезов Vue'",
  `    include ${slices.map(id).join(", ")}`,
  "  }",
  "}",
  "",
);
await writeFile("architecture/modules.c4", lines.join("\n"));
console.log(
  `Architecture synchronized: ${files.length} source files, ${slices.length} slices.`,
);
