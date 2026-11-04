import { writeFile } from "node:fs/promises";
import { graph, slice } from "./source-graph.mjs";
const { files, edges } = await graph();
const slices = [...new Set(files.map(slice))];
const id = (s) => s.replaceAll(/[^a-zA-Z0-9_]/g, "_");
const notes = {
  app: "Инициализация Vue, Router, Pinia; выбор HTTP или локального демо-адаптера.",
  "pages/catalog": "Поиск санатория по категории и карте, без выбора дат.",
  "pages/resort-profile":
    "Профиль санатория, выбор дат, доступные номера и отзывы.",
  "pages/room-profile": "Профиль физического номера, медиа, описание и тарифы.",
  "pages/my-bookings":
    "Гостевые заявки, демонстрационная оплата, отмена и отзыв.",
  "pages/analytics": "Scoped аналитика событий, периоды, графики и разрезы.",
  "pages/guest-profile":
    "Сессионный контакт гостя и история бронирований/оплат.",
  "pages/receipt": "Демо-квитанция и отдельные сведения о возврате.",
  "pages/staff-guest": "Профиль гостя с историей только доступных санаториев.",
  "features/payment-receipt":
    "Скачивание PDF и передача файла по действию пользователя.",
  "pages/workspace": "Кабинет: реестры, фильтры, действия и история изменений.",
  "pages/login": "Выбор демо-аккаунта или форма серверного входа в режиме api.",
  "entities/session": "Pinia: текущий пользователь и роль.",
  "entities/resort": "Pinia: санатории, физические комнаты и тарифы.",
  "entities/booking": "Pinia: брони и чистые правила дат.",
  "shared/api":
    "Контракт транспорта, ошибки, HTTP fetch с cookies и сохранение форм.",
  "features/demo-payment": "Симуляция результата оплаты без обращения к банку.",
  "features/review-form": "Отзыв по завершённой брони и загрузка фотографий.",
  "widgets/public-header": "Навигация гостя и категории каталога.",
  "widgets/media-gallery": "Галерея фотографий и видео профиля.",
  "shared/ui": "Общие native dialog, карта Leaflet и редактор медиа.",
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
