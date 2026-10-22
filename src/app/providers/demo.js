import {
  resorts as seedResorts,
  tariffs as seedTariffs,
} from "./seed-catalog.js";
import {
  dateAfter,
  validateSearch,
  overlaps,
  nightsBetween,
} from "../../entities/booking/rules.js";
import { ApiError } from "../../shared/api/index.js";
export const DATABASE_KEY = "tynys:workspace:v2";
export const SESSION_KEY = "tynys:session:v2";
const clone = (value) => JSON.parse(JSON.stringify(value));
const fail = (message, status = 422) => {
  throw new ApiError(message, status);
};
const text = (value, label, max = 200, required = true) => {
  if (
    typeof value !== "string" ||
    (required && !value.trim()) ||
    value.trim().length > max
  )
    fail(`${label}: заполните поле (до ${max} символов).`);
  return value.trim();
};
const number = (value, label, min, max, integer = false) => {
  if (value === "" || value == null) fail(`${label}: укажите число.`);
  const n = Number(value);
  if (
    !Number.isFinite(n) ||
    n < min ||
    n > max ||
    (integer && !Number.isInteger(n))
  )
    fail(`${label}: допустимо от ${min} до ${max}.`);
  return n;
};
const choice = (value, values) => {
  if (!values.includes(value)) fail("Недопустимое значение.");
  return value;
};
function initialState(legacy = []) {
  const db = {
    schema: 2,
    revision: 0,
    clientId: crypto.randomUUID(),
    resorts: [],
    rooms: [],
    tariffs: [],
    bookings: [],
    accounts: [],
    audit: [],
  };
  db.accounts = [
    {
      id: "admin",
      name: "Администратор платформы",
      login: "admin@demo.tynys",
      role: "admin",
      resortId: null,
      status: "active",
      version: 1,
    },
    {
      id: "manager-altun",
      name: "Айдана · Altyn Bulak",
      login: "altyn@demo.tynys",
      role: "manager",
      resortId: "altun",
      status: "active",
      version: 1,
    },
    {
      id: "manager-arasan",
      name: "Данияр · Arasan",
      login: "arasan@demo.tynys",
      role: "manager",
      resortId: "arasan",
      status: "active",
      version: 1,
    },
  ];
  for (const r of seedResorts) {
    db.resorts.push({
      id: r.id,
      name: r.name,
      subtitle: r.subtitle,
      description: r.description,
      city: "Сарыагаш",
      address: "Курортная зона, Коктерек",
      lat: r.lat,
      lng: r.lng,
      feature: r.feature,
      rating: r.rating,
      status: "published",
      version: 1,
    });
    for (const type of r.rooms)
      for (const unit of type.units)
        db.rooms.push({
          id: `${r.id}-${unit}`,
          resortId: r.id,
          number: unit,
          category: type.category,
          title: type.title,
          area: type.area,
          capacity: type.capacity,
          beds: type.beds,
          price: type.price,
          status: "active",
          version: 1,
        });
    for (const t of seedTariffs)
      db.tariffs.push({
        ...t,
        id: `${r.id}-${t.id}`,
        resortId: r.id,
        status: "active",
        version: 1,
      });
  }
  for (const b of legacy) {
    const room = db.rooms.find(
      (r) => r.resortId === b.resortId && r.number === b.unit,
    );
    const tariff = db.tariffs.find(
      (t) => t.id === `${b.resortId}-${b.tariffId}`,
    );
    if (!room || !tariff) continue;
    db.bookings.push({
      ...b,
      roomId: room.id,
      tariffId: tariff.id,
      guestLabel: "Гость сайта",
      source: "website",
      ownerId: db.clientId,
      version: 1,
    });
  }
  db.audit.push({
    id: crypto.randomUUID(),
    at: new Date().toISOString(),
    actor: "Демо-система",
    resortId: null,
    entity: "system",
    entityId: "seed",
    action: "create",
    label: "Подготовлен демонстрационный каталог",
    before: null,
    after: null,
  });
  return db;
}
export function createDemoTransport({
  storage = localStorage,
  session = sessionStorage,
  delay = 120,
} = {}) {
  const read = () => {
    let db;
    try {
      const raw = storage.getItem(DATABASE_KEY);
      if (raw) db = JSON.parse(raw);
      else {
        const legacy = JSON.parse(storage.getItem("tynys:bookings:v1") || "[]");
        if (!Array.isArray(legacy)) throw new Error();
        db = initialState(legacy);
        storage.setItem(DATABASE_KEY, JSON.stringify(db));
      }
      if (
        db.schema !== 2 ||
        !["resorts", "rooms", "tariffs", "bookings", "accounts", "audit"].every(
          (k) => Array.isArray(db[k]),
        ) ||
        !db.clientId
      )
        throw new Error();
    } catch {
      fail(
        "Локальное хранилище недоступно или данные повреждены. Включите хранение данных либо откройте демо в другом профиле браузера.",
        503,
      );
    }
    return db;
  };
  const userFor = (db) => {
    let id;
    try {
      id = session.getItem(SESSION_KEY);
    } catch {
      fail("Хранилище сессии недоступно.", 503);
    }
    return (
      db.accounts.find((a) => a.id === id && a.status === "active") || null
    );
  };
  const execute = (method, path, payload = {}) => {
    const db = read();
    const user = userFor(db);
    const [pathname, query] = path.split("?");
    const params = new URLSearchParams(query);
    const publicResorts = db.resorts.filter((r) => r.status === "published");
    const isPublic = (id) => publicResorts.some((r) => r.id === id);
    const authorize = (resortId) => {
      if (!user) fail("Войдите в кабинет сотрудника.", 401);
      if (user.role !== "admin" && user.resortId !== resortId)
        fail("У вас нет доступа к этому санаторию.", 403);
    };
    const admin = () => {
      if (!user) fail("Войдите в кабинет.", 401);
      if (user.role !== "admin")
        fail("Действие доступно только администратору платформы.", 403);
    };
    const scoped = (item) =>
      user?.role === "admin" || (user && item.resortId === user.resortId);
    const version = (item) => {
      if (payload.version !== item.version)
        fail(
          "Запись изменена в другой вкладке. Обновите список и откройте форму заново.",
          409,
        );
    };
    const commit = (entity, after, before = null, action = "create") => {
      const resortId =
        entity === "resorts"
          ? (after || before).id
          : (after || before)?.resortId;
      db.audit.unshift({
        id: crypto.randomUUID(),
        at: new Date().toISOString(),
        actor: pathname.startsWith("/my-bookings")
          ? "Гость сайта"
          : user?.name || "Демо-система",
        resortId,
        entity,
        entityId: (after || before).id,
        action,
        label:
          (after || before).name ||
          (after || before).number ||
          (after || before).guestLabel ||
          (after || before).id,
        before: clone(before),
        after: clone(after),
      });
      db.revision++;
      try {
        storage.setItem(DATABASE_KEY, JSON.stringify(db));
      } catch {
        fail(
          "Не удалось сохранить изменения. Проверьте свободное место и разрешение на хранение данных.",
          503,
        );
      }
      return clone(after);
    };
    if (pathname === "/auth/session" && method === "GET") return clone(user);
    if (pathname === "/demo/accounts" && method === "GET")
      return clone(
        db.accounts
          .filter((a) => a.status === "active")
          .map(({ id, name, role, login, resortId }) => ({
            id,
            name,
            role,
            login,
            resortId,
          })),
      );
    if (pathname === "/auth/login" && method === "POST") {
      const account = db.accounts.find(
        (a) => a.id === payload.accountId && a.status === "active",
      );
      if (!account) fail("Демо-аккаунт не найден или отключён.", 401);
      session.setItem(SESSION_KEY, account.id);
      return clone(account);
    }
    if (pathname === "/auth/logout" && method === "POST") {
      session.removeItem(SESSION_KEY);
      return null;
    }
    if (pathname === "/catalog" && method === "GET")
      return clone({
        resorts: publicResorts,
        rooms: db.rooms.filter(
          (r) => isPublic(r.resortId) && r.status === "active",
        ),
        tariffs: db.tariffs.filter(
          (t) => isPublic(t.resortId) && t.status === "active",
        ),
      });
    if (pathname === "/availability" && method === "GET") {
      const search = {
        start: params.get("start"),
        end: params.get("end"),
        guests: Number(params.get("guests")),
      };
      const error = validateSearch(search);
      if (error) fail(error);
      return {
        roomIds: db.rooms
          .filter(
            (r) =>
              isPublic(r.resortId) &&
              r.status === "active" &&
              r.capacity >= search.guests &&
              !db.bookings.some(
                (b) =>
                  b.roomId === r.id &&
                  b.status === "confirmed" &&
                  overlaps(b, search),
              ),
          )
          .map((r) => r.id),
      };
    }
    if (pathname === "/workspace" && method === "GET") {
      if (!user) fail("Войдите в кабинет сотрудника.", 401);
      return clone({
        resorts: db.resorts.filter(
          (r) => user.role === "admin" || r.id === user.resortId,
        ),
        rooms: db.rooms.filter(scoped),
        tariffs: db.tariffs.filter(scoped),
        bookings: db.bookings.filter(scoped),
        accounts:
          user.role === "admin"
            ? db.accounts.filter((a) => a.role === "manager")
            : [],
        audit: db.audit.filter(scoped),
      });
    }
    if (pathname === "/my-bookings" && method === "GET")
      return clone(db.bookings.filter((b) => b.ownerId === db.clientId));
    const match = pathname.match(
      /^\/(resorts|rooms|tariffs|accounts|bookings|my-bookings)(?:\/([^/]+))?$/,
    );
    if (!match) fail("Маршрут API не найден.", 404);
    const [, kind, id] = match;
    const entity = kind === "my-bookings" ? "bookings" : kind;
    const collection = db[entity];
    const item = id ? collection.find((x) => x.id === id) : null;
    if (id && !item) fail("Запись не найдена. Обновите список.", 404);
    if (entity === "bookings") {
      if (method === "POST") {
        const room = db.rooms.find((r) => r.id === payload.roomId);
        const tariff = db.tariffs.find((t) => t.id === payload.tariffId);
        if (!room || !tariff || tariff.resortId !== room.resortId)
          fail("Выберите номер и тариф одного санатория.");
        const resort = db.resorts.find((r) => r.id === room.resortId);
        if (kind === "bookings") authorize(room.resortId);
        else if (!isPublic(room.resortId))
          fail("Санаторий недоступен для бронирования.");
        if (
          resort.status === "archived" ||
          room.status !== "active" ||
          tariff.status !== "active"
        )
          fail("Номер или тариф сейчас недоступен.");
        const search = {
          start: payload.start,
          end: payload.end,
          guests: Number(payload.guests),
        };
        const error = validateSearch(search);
        if (error) fail(error);
        if (search.guests > room.capacity)
          fail("Вместимость номера меньше числа гостей.");
        if (
          db.bookings.some(
            (b) =>
              b.roomId === room.id &&
              b.status === "confirmed" &&
              overlaps(b, search),
          )
        )
          fail(
            "Номер занят на выбранные даты. Выберите другой номер или даты.",
            409,
          );
        const nightly = room.price + tariff.supplement * search.guests;
        const booking = {
          id: crypto.randomUUID(),
          resortId: room.resortId,
          roomId: room.id,
          tariffId: tariff.id,
          resortName: resort.name,
          roomName: room.title,
          unit: room.number,
          tariffName: tariff.name,
          ...search,
          nightly,
          nights: nightsBetween(search.start, search.end),
          total: nightly * nightsBetween(search.start, search.end),
          guestLabel:
            kind === "bookings"
              ? text(payload.guestLabel, "Обозначение гостя", 80)
              : "Гость сайта",
          source: kind === "bookings" ? "staff" : "website",
          ownerId: kind === "bookings" ? null : db.clientId,
          status: "confirmed",
          version: 1,
          createdAt: new Date().toISOString(),
        };
        collection.push(booking);
        return commit(entity, booking);
      }
      if (method === "PATCH" && item) {
        if (kind === "my-bookings") {
          if (item.ownerId !== db.clientId)
            fail("Эта бронь вам недоступна.", 403);
        } else authorize(item.resortId);
        version(item);
        if (payload.status !== "cancelled" || item.status !== "confirmed")
          fail("Можно отменить только подтверждённую бронь.");
        const before = clone(item);
        item.status = "cancelled";
        item.version++;
        return commit(entity, item, before, "cancel");
      }
      fail("Бронирования сохраняются в истории. Используйте отмену.", 405);
    }
    if (entity === "accounts") admin();
    else if (entity === "resorts") {
      if (method === "POST" || method === "DELETE") admin();
      else authorize(id);
    } else authorize(item?.resortId || payload.resortId);
    if (item) version(item);
    if (method === "DELETE" && item) {
      if (entity === "resorts") {
        if (
          db.bookings.some(
            (b) =>
              b.resortId === id &&
              b.status === "confirmed" &&
              b.end > dateAfter(),
          )
        )
          fail("Сначала отмените текущие и будущие бронирования.");
        const before = clone(item);
        item.status = "archived";
        item.version++;
        return commit(entity, item, before, "archive");
      }
      if (entity === "accounts") fail("Используйте отключение аккаунта.", 405);
      if (
        db.bookings.some((b) =>
          entity === "rooms" ? b.roomId === id : b.tariffId === id,
        )
      )
        fail(
          "Запись связана с историей бронирований. Измените статус вместо удаления.",
        );
      collection.splice(collection.indexOf(item), 1);
      return commit(entity, null, item, "delete");
    }
    if (!["POST", "PATCH"].includes(method) || (method === "PATCH" && !item))
      fail("Операция недоступна.", 405);
    const resortId =
      entity === "accounts"
        ? payload.resortId
        : item?.resortId || payload.resortId;
    if (["rooms", "tariffs", "accounts"].includes(entity)) {
      const resort = db.resorts.find((r) => r.id === resortId);
      if (!resort || resort.status === "archived")
        fail("Выберите действующий санаторий.");
    }
    let fields;
    if (entity === "resorts") {
      fields = {
        name: text(payload.name, "Название", 100),
        city: text(payload.city, "Город", 80),
        address: text(payload.address, "Адрес"),
        description: text(payload.description, "Описание", 2000, false),
        subtitle: text(payload.subtitle, "Краткое описание", 160, false),
        feature: text(payload.feature || "Отдых", "Услуга", 80),
        lat: number(payload.lat, "Широта", -90, 90),
        lng: number(payload.lng, "Долгота", -180, 180),
        status: choice(payload.status, ["draft", "published"]),
      };
      if (
        fields.status === "published" &&
        (!item ||
          !db.rooms.some((r) => r.resortId === id && r.status === "active") ||
          !db.tariffs.some((t) => t.resortId === id && t.status === "active"))
      )
        fail(
          "Перед публикацией добавьте хотя бы один активный номер и тариф. Сначала сохраните черновик.",
        );
    }
    if (entity === "rooms") {
      fields = {
        resortId,
        number: text(payload.number, "Номер комнаты", 20),
        category: choice(payload.category, ["standard", "comfort", "suite"]),
        title: text(payload.title, "Название категории", 80),
        area: number(payload.area, "Площадь", 5, 500),
        capacity: number(payload.capacity, "Вместимость", 1, 4, true),
        beds: text(payload.beds, "Кровати", 120),
        price: number(payload.price, "Цена", 0, 10000000, true),
        status: choice(payload.status, ["active", "maintenance"]),
      };
      if (
        db.rooms.some(
          (r) =>
            r.resortId === resortId &&
            r.number.toLowerCase() === fields.number.toLowerCase() &&
            r.id !== id,
        )
      )
        fail("Комната с таким номером уже существует.");
      const future = db.bookings.filter(
        (b) =>
          b.roomId === id && b.status === "confirmed" && b.end > dateAfter(),
      );
      if (
        (fields.status === "maintenance" && future.length) ||
        future.some((b) => b.guests > fields.capacity)
      )
        fail(
          "Изменение конфликтует с текущими или будущими бронями. Сначала отмените их.",
        );
    }
    if (entity === "tariffs")
      fields = {
        resortId,
        name: text(payload.name, "Название", 80),
        description: text(payload.description, "Описание", 400, false),
        supplement: number(payload.supplement, "Доплата", 0, 10000000, true),
        features: text(payload.features || "", "Услуги", 400, false)
          .split("\n")
          .map((v) => v.trim())
          .filter(Boolean),
        status: choice(payload.status, ["active", "disabled"]),
      };
    if (entity === "accounts") {
      fields = {
        resortId,
        name: text(payload.name, "Имя", 100),
        login: text(payload.login, "Логин", 100).toLowerCase(),
        role: "manager",
        status: choice(payload.status, ["active", "disabled"]),
      };
      if (
        db.accounts.some(
          (a) => a.login.toLowerCase() === fields.login && a.id !== id,
        )
      )
        fail("Этот логин уже занят.");
    }
    const before = item ? clone(item) : null;
    const after = {
      ...(item || {
        id: crypto.randomUUID(),
        ...(entity === "resorts" ? { rating: 0 } : {}),
      }),
      ...fields,
      version: (item?.version || 0) + 1,
    };
    if (item) collection.splice(collection.indexOf(item), 1, after);
    else collection.push(after);
    return commit(entity, after, before, item ? "update" : "create");
  };
  return async (method, path, body) => {
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    if (
      typeof window !== "undefined" &&
      globalThis.navigator?.locks &&
      method !== "GET"
    )
      return navigator.locks.request(DATABASE_KEY, () =>
        execute(method, path, body),
      );
    return execute(method, path, body);
  };
}
